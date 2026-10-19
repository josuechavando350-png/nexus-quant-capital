"""Offline structural decode of Nitro blobs. Not an ArbOS execution engine."""
from pathlib import Path
import json
import hashlib
from collections import Counter
import brotli
from Crypto.Hash import keccak

ROOT = Path(__file__).resolve().parents[1]

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def k256(raw):
    return keccak.new(digest_bits=256, data=raw).digest()

def rlp_one(raw, start=0, depth=0):
    require(depth <= 32 and start < len(raw), 'truncated/deep RLP')
    lead = raw[start]
    if lead < 128:
        return raw[start:start+1], start+1
    is_list = lead >= 192
    short = 192 if is_list else 128
    long = 247 if is_list else 183
    if lead <= long:
        n = lead-short
        p = start+1
    else:
        size = lead-long
        require(start+1+size <= len(raw), 'truncated RLP length')
        digits = raw[start+1:start+1+size]
        require(digits[0] != 0, 'RLP leading zero length')
        n = int.from_bytes(digits, 'big')
        require(n >= 56, 'noncanonical long RLP')
        p = start+1+size
    end = p+n
    require(end <= len(raw), 'truncated RLP value')
    if not is_list:
        out = raw[p:end]
        require(not (n == 1 and out[0] < 128), 'noncanonical short RLP')
        return out, end
    values = []
    while p < end:
        value, p = rlp_one(raw, p, depth+1)
        require(p <= end, 'RLP child crosses list')
        values.append(value)
    return values, end

def decode_blobs(blobs):
    encoded = bytearray()
    for blob in blobs:
        require(len(blob) == 131072, 'wrong blob length')
        require(all(blob[i] < 64 for i in range(0, len(blob), 32)), 'Nitro high bits')
        for i in range(0, len(blob), 32):
            encoded.extend(blob[i+1:i+32])
        acc = bits = 0
        for i in range(0, len(blob), 32):
            acc |= blob[i] << bits
            bits += 6
            if bits >= 8:
                encoded.append(acc & 255)
                acc >>= 8
                bits -= 8
        require(bits == 0, 'unconsumed bits')
    value, end = rlp_one(encoded)
    require(isinstance(value, (bytes, bytearray)), 'blob RLP must be bytes')
    # Stricter than upstream's first-value decoder: reject hidden trailing bytes.
    require(not any(encoded[end:]), 'nonzero blob padding')
    return bytes(value), len(encoded)-end

def decompress_limited(raw, limit=16*1024*1024):
    decoder = brotli.Decompressor()
    out = bytearray()
    for offset in range(0, len(raw), 256):
        out.extend(decoder.process(raw[offset:offset+256]))
        require(len(out) <= limit, 'decompression limit')
    require(decoder.is_finished(), 'incomplete Brotli stream')
    return bytes(out)

def segments_from_payload(payload):
    require(payload and payload[0] == 0, 'unsupported batch compression')
    raw = decompress_limited(payload[1:])
    segments = []
    pos = 0
    while pos < len(raw):
        value, pos = rlp_one(raw, pos)
        require(isinstance(value, bytes) and value, 'invalid/empty segment')
        segments.append(value)
        require(len(segments) <= 102400, 'too many segments')
    return segments, raw

def signed_txs(message, depth=0):
    require(message and depth <= 16, 'empty/deep L2 message')
    kind, data = message[0], message[1:]
    if kind == 4:
        tx_type = data[0] if data and data[0] < 128 else 0
        require(tx_type in (0, 1, 2, 4), 'unsupported signed tx type')
        fields, end = rlp_one(data, 1 if tx_type else 0)
        require(isinstance(fields, list) and end == len(data), 'invalid tx RLP')
        yield data
    elif kind == 3:
        pos = 0
        while pos < len(data):
            require(pos+8 <= len(data), 'truncated nested L2 length')
            size = int.from_bytes(data[pos:pos+8], 'big')
            pos += 8
            require(size > 0 and pos+size <= len(data), 'truncated nested L2 message')
            yield from signed_txs(data[pos:pos+size], depth+1)
            pos += size
    else:
        raise ValueError('unsupported L2 message kind '+str(kind))

def decode(blobs):
    payload, padding = decode_blobs(blobs)
    segments, expanded = segments_from_payload(payload)
    messages = []
    timestamp = l1block = 0
    for segment_index, segment in enumerate(segments):
        kind, data = segment[0], segment[1:]
        if kind in (3, 4):
            v, end = rlp_one(data)
            require(isinstance(v, bytes) and len(v) <= 8 and end == len(data), 'advance encoding')
            require(not v or v[0] != 0, 'advance leading zero')
            if kind == 3:
                timestamp += int.from_bytes(v, 'big')
            else:
                l1block += int.from_bytes(v, 'big')
        elif kind in (0, 1):
            if kind == 1:
                data = decompress_limited(data)
            txs = list(signed_txs(data))
            messages.append({'ordinal':len(messages), 'segment_index':segment_index,
                             'timestamp_before_l1_bounds':timestamp,
                             'l1block_before_l1_bounds':l1block,
                             'tx_hashes':['0x'+k256(tx).hex() for tx in txs],
                             'raw_transactions':txs})
        else:
            raise ValueError('unsupported batch segment kind '+str(kind))
    return {'payload_bytes':len(payload), 'expanded_bytes':len(expanded),
            'padding_bytes':padding, 'segment_count':len(segments),
            'segment_kinds':dict(Counter(s[0] for s in segments)), 'messages':messages}

def main():
    blobs = [(ROOT/f'evidence/blob-{i}-payload.response').read_bytes() for i in range(3)]
    decoded = decode(blobs)
    target = json.loads((ROOT/'inputs/05-block.json').read_text())['result']
    target_tx = target['transactions'][1]
    matches = [m for m in decoded['messages'] if target_tx in m['tx_hashes']]
    summary = {k:v for k,v in decoded.items() if k != 'messages'}
    summary.update({'message_count':len(decoded['messages']),
                    'signed_transaction_count':sum(len(m['tx_hashes']) for m in decoded['messages']),
                    'target_matches':[]})
    for m in matches:
        (ROOT/'evidence/target-message-transactions.json').write_text(json.dumps(
            {k: (['0x'+v.hex() for v in value] if k=='raw_transactions' else value) for k,value in m.items()},indent=2)+'\n')
        row={k:v for k,v in m.items() if k not in ('raw_transactions','tx_hashes')}
        row.update({'tx_count':len(m['tx_hashes']), 'target_index_within_message':m['tx_hashes'].index(target_tx),
                    'matches_captured_block_transactions_excluding_system_tx0':m['tx_hashes']==target['transactions'][1:]})
        summary['target_matches'].append(row)
    summary.update({'full_l2_header_derived':False,'exact_prestate_authenticated':False,'commercial_admission':False})
    (ROOT/'evidence/DECODE_RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__ == '__main__':
    main()
