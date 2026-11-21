"""Verify lossless transport of NQC's approved catalog through a fixed byte-token vocabulary."""
import ast
import json
from pathlib import Path
import shutil
import sys
import tempfile

from .product_census_header import pinned
from .product_languages_batch import run
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .safe_io import canonical, strict_json

VLLM = 'vllm-project/vllm'
LLAMA = 'ggml-org/llama.cpp'
SGLANG = 'sgl-project/sglang'
CATALOG = 'superhunter/repositories_200.json'
CATALOG_SHA = 'b09440d99064c283e53acb5f5ee34a62dc59338ad6fe090d4978e2b562806449'
ARCHIVE = 'superhunter/product_supply/review-117-session.json'
RUSTC_SHA = '859254978c0a0402c32f949f6de0d99aee73be8d15f45aac00ae1448aac51e74'
ARCHIVE_SHA = 'f242a9ec30a3b70c4d2079c416b63c9fb96af06d2fc1c809d1dead89be1d7963'
PROJECTS = {
    VLLM: ('161-vllm', '1bdc437402d6eee29d3ca543c91574f8acc72c8d',
           'rust/src/tokenizer/src/byte_level_decode.rs', 'f3d6a571633104c8c5cf72887c944376916130ca0df8f005d8381066f5fb7c93'),
    LLAMA: ('162-llama.cpp', 'e6d624b9a4b95c6b52f5ca384d70b75581f9821a',
            'gguf-py/gguf/vocab.py', 'fce519b621f873213973c8186b010d7c41d6bb22134e411c8d47bf3a3e63f807'),
    SGLANG: ('163-sglang', '4ce41378f96da24f12e76eae35dfea5bbf35844a',
             'sgl-router/tests/fixtures/tiny_tokenizer.json', '1d8d1215928cec15e26eb08947fbae04368c4b097ca28137470165dd81cefaaa'),
}
DRIVER = """mod decoder;
use std::io::{self, BufRead};
use std::fmt::Write;

fn main() -> io::Result<()> {
    for line in io::stdin().lock().lines() {
        let line = line?;
        let tokens = line.char_indices().map(|(i, c)| &line[i..i + c.len_utf8()]);
        let mut hex = String::new();
        for byte in decoder::decode_byte_level(tokens).bytes() {
            write!(hex, "{:02x}", byte).unwrap();
        }
        println!("{}", hex);
    }
    Ok(())
}
"""


def inputs(root):
    files = {}
    for name, (folder, revision, path, digest) in PROJECTS.items():
        checkout = root / folder
        if not checkout.is_dir() or checkout.is_symlink():
            raise EvidenceError('missing reviewed evidence codec checkout for ' + name)
        if git(checkout, 'rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('unexpected evidence codec checkout for ' + name)
        raw = pinned(checkout, path, digest)
        if git(checkout, 'show', revision + ':' + path) != raw:
            raise EvidenceError('evidence codec file differs from its Git object')
        files[name] = raw
    return files


def catalog_records():
    from .tools.verify_review_115 import unpack
    entries = strict_json(pinned(ROOT, CATALOG, CATALOG_SHA))['entries']
    lines = unpack(pinned(ROOT, ARCHIVE, ARCHIVE_SHA)).splitlines()
    if len(lines) != 220:
        raise EvidenceError('unexpected PR 117 query transcript')
    archived = strict_json(lines[213])['rows']  # integration-matrix in the fixed 220-query profile
    records = []
    for index, (row, witness) in enumerate(zip(entries, archived, strict=True), 1):
        if (row['id'], row['repository']) != (index, witness['repository']) or witness['id'] != index:
            raise EvidenceError('archived proof identity differs from approved catalog')
        record = {key: row[key] for key in ('id', 'repository', 'purpose')}
        record.update({key: witness[key] for key in ('commit', 'session', 'receipt', 'session_evidence_sha256')})
        records.append(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
    if len(records) != 200:
        raise EvidenceError('incomplete catalog evidence')
    return records


def encode_alphabet(work, raw):
    # Use the exact standalone conversion routine, without importing the unrelated ML stack.
    source = raw.decode()
    node, = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'bytes_to_unicode']
    if node.decorator_list:
        raise EvidenceError('unexpected conversion dependencies')
    function = ast.get_source_segment(source, node)
    probe = function + '\nimport json\nalphabet = bytes_to_unicode()\nprint(json.dumps([alphabet[i] for i in range(256)]))\n'
    result = json.loads(run(work, [sys.executable, '-I', '-S', '-B', '-c', probe]))
    if len(result) != 256 or len(set(result)) != 256 or any(len(label) != 1 for label in result):
        raise EvidenceError('invalid byte-to-label map')
    return result


def vocabulary(raw, alphabet):
    config = strict_json(raw)
    vocab = config['model']['vocab']
    if (config['decoder']['type'] != 'ByteLevel' or config['pre_tokenizer']['add_prefix_space']
            or config['model']['merges'] or len(vocab) != 257):
        raise EvidenceError('unsupported tokenizer profile')
    if any(type(vocab.get(label)) is not int or vocab[label] != byte for byte, label in enumerate(alphabet)):
        raise EvidenceError('SGLang token identities disagree with llama.cpp byte labels')
    special, = config['added_tokens']
    if (special['special'] is not True or special['id'] != 256
            or special['content'] != '<|endoftext|>' or vocab[special['content']] != 256):
        raise EvidenceError('reserved token declaration differs')
    return vocab


def labels_for(ids, inverse):
    if any(type(token) is not int or not 0 <= token < 256 for token in ids):
        raise EvidenceError('non-evidence token in stream')
    return ''.join(inverse[token] for token in ids)


def compatible(decoded, original):
    if sha(decoded) != sha(original):
        return False
    return strict_json(decoded) == strict_json(original)


def review(source_root):
    files = inputs(Path(source_root))
    records = catalog_records()
    rustc = shutil.which('rustc')
    if rustc is None:
        raise EvidenceError('the evidence decoder requires rustc on PATH')
    compiler = Path(rustc).resolve(strict=True)
    pinned(compiler.parent, compiler.name, RUSTC_SHA)
    with tempfile.TemporaryDirectory(prefix='nqc-evidence-codec-') as directory:
        work = Path(directory)
        alphabet = encode_alphabet(work, files[LLAMA])
        vocab = vocabulary(files[SGLANG], alphabet)
        inverse = {number: token for token, number in vocab.items()}
        encoded = [[vocab[alphabet[byte]] for byte in row] for row in records]
        # The fixture assigns one ID to each original byte, an oracle independent of the decoder.
        if any(bytes(ids) != raw for ids, raw in zip(encoded, records, strict=True)):
            raise EvidenceError('encoded stream differs from its source bytes')
        witness_index = next(i for i, record in enumerate(records) if strict_json(record)['receipt'])
        altered = strict_json(records[witness_index])
        altered['session_evidence_sha256'] = '0' * 64
        altered_bytes = json.dumps(altered, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        controls = {
            'changed_receipt': (witness_index, [vocab[alphabet[b]] for b in altered_bytes]),
            'truncated': (0, encoded[0][:-1]),
            'other_identity': (0, encoded[1]),
            'broken_utf8': (0, [0xc3]),
        }
        for control in ([-1], [256], [False], [257]):
            try:
                labels_for(control, inverse)
            except EvidenceError:
                continue
            raise EvidenceError('reserved or invalid token passed the decoder gate')
        streams = [labels_for(seq, inverse) for seq in encoded]
        streams.extend(labels_for(seq, inverse) for _, seq in controls.values())
        (work / 'decoder.rs').write_bytes(files[VLLM])
        (work / 'main.rs').write_text(DRIVER)
        run(work, [str(compiler), '--edition=2021', '-C', 'debuginfo=0', 'main.rs', '-o', 'decode'])
        output = run(work, ['./decode'], ('\n'.join(streams) + '\n').encode()).splitlines()
    if len(output) != len(streams):
        raise EvidenceError('decoder result cardinality differs')
    recovered = [bytes.fromhex(line.decode('ascii')) for line in output]
    accepted = [strict_json(row)['id'] for row, original in zip(recovered[:len(records)], records, strict=True)
                if compatible(row, original)]
    rejected = {name: not compatible(data, records[index])
                for (name, (index, _)), data in zip(controls.items(), recovered[len(records):], strict=True)}
    admitted = [strict_json(raw) for raw in recovered[:len(records)]]
    ledger = {entry['repository']: entry['session_evidence_sha256'] for entry in admitted if entry['receipt']}
    if len(ledger) != 59 or any(len(digest) != 64 for digest in ledger.values()):
        raise EvidenceError('decoded evidence cannot restore the archived receipt index')
    if (accepted != list(range(1, 201)) or not all(rejected.values())
            or recovered[-1] != '\ufffd'.encode()):
        raise EvidenceError('evidence transport or its negative controls differed')

    admissions = sha(canonical([sha(data) for data in recovered[:len(records)]]))
    result = {
        LLAMA: ('execution', 'encode_owned_catalog_evidence_labels',
                {'byte_labels_sha256': sha(canonical(alphabet)), 'source_bytes': sum(map(len, records)),
                 'catalog_sha256': CATALOG_SHA, 'historical_input_sha256': ARCHIVE_SHA, 'records': len(records)}),
        SGLANG: ('reference', 'map_evidence_labels_to_router_fixture_ids',
                 {'streams_sha256': sha(canonical(encoded)), 'records': len(encoded),
                  'reserved_ids_rejected': [256], 'byte_id_parity': 256}),
        VLLM: ('execution', 'decode_and_admit_owned_catalog_evidence_records',
               {'admitted_records': len(accepted), 'decoded_digests_sha256': admissions,
                'restored_receipts': len(ledger), 'receipt_index_sha256': sha(canonical(ledger)),
                'negative_controls_rejected': rejected, 'malformed_utf8_replacement': 'U+FFFD'}),
    }
    return {name: {'revision': PROJECTS[name][1], 'source_sha256': PROJECTS[name][3], 'role': role,
                   'operation': operation, 'result': details}
            for name, (role, operation, details) in result.items()}
