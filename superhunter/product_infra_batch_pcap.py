"""Convert authenticated PCAP/PCAPNG regression evidence into an NQC forensic timeline."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from . import forensic_timeline as forensic
from . import infra_batch_pcap_worker as worker
from .product_infra_batch import capture
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import sha
from .safe_io import canonical, strict_json

WIRESHARK = 'wireshark/wireshark'
SCAPY = 'secdev/scapy'
TCPDUMP = 'the-tcpdump-group/tcpdump'
DHCP = worker.NAMES[:4]
NTP = 'ntp-time.pcap'
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
BILLION = 1_000_000_000
SOURCES = {
    WIRESHARK: ('091-wireshark', '2276442166317e2d80346cf0eb2f2744dd17c6c2',
                tuple('test/captures/' + name for name in DHCP) + ('test/baseline/ff-ts-usec-pcap-direct.txt',)),
    SCAPY: ('092-scapy', '3813c08c414a30c686136e50c6e80dd9b3b29663',
            tuple('scapy/' + n + '.py' for n in ('__init__', 'base_classes', 'compat', 'config', 'consts',
                                                  'dadict', 'data', 'error', 'main', 'pton_ntop', 'themes', 'utils'))),
    TCPDUMP: ('095-tcpdump', '3541bd5d38635e208d7dd47cc6ea2af00dd7ef0c',
              ('tests/ntp-time.pcap', 'tests/ntp-time.out')),
}


def classic(raw):
    """Independent, bounded reader for little-endian classic PCAP, full Ethernet records only."""
    if len(raw) < 24:
        raise EvidenceError('short PCAP header')
    magic, major, minor, _, _, snaplen, link = struct.unpack_from('<IHHIIII', raw)
    if (magic, major, minor, link) != (0xa1b2c3d4, 2, 4, 1):
        raise EvidenceError('unexpected classic PCAP header')
    frames = []
    pos = 24
    while pos < len(raw):
        if len(raw) - pos < 16:
            raise EvidenceError('short PCAP record header')
        sec, usec, size, wire = struct.unpack_from('<IIII', raw, pos)
        pos += 16
        if size != wire or not 0 < size <= min(snaplen, len(raw) - pos) or usec >= 1_000_000:
            raise EvidenceError('truncated PCAP record or invalid length/time')
        frame = raw[pos:pos + size]
        frames.append(({'epoch_ns': sec * BILLION + usec * 1000, 'captured': size,
                        'wire': wire, 'frame_sha256': sha(frame)}, frame))
        pos += size
    return frames


def ntp_records(frames):
    observed = []
    for row, frame in frames:
        if frame[12:14] != b'\x08\x00' or frame[14] != 0x45 or frame[23] != 17:
            raise EvidenceError('unexpected NTP regression transport')
        udp_start = 34
        src, dst, size = struct.unpack_from('!HHH', frame, udp_start)
        flags = frame[udp_start + 8]
        mode = {3: 'Client', 4: 'Server'}.get(flags & 7)
        if not mode or (dst if mode == 'Client' else src) != 123 or size != len(frame) - udp_start:
            raise EvidenceError('invalid archived NTP record')
        observed.append((row['epoch_ns'], (flags >> 3) & 7, mode, size - 8))
    return observed


def check_data(decoded, wifi, tcp):
    reference = classic(wifi['test/captures/dhcp.pcap'])
    dhcp = [row for row, _ in reference]
    baseline = wifi['test/baseline/ff-ts-usec-pcap-direct.txt'].decode().splitlines()
    previous = None
    for ordinal, (line, row) in enumerate(zip(baseline, dhcp, strict=True), 1):
        seq, timestamp, delta = line.split('\t')
        epoch = row['epoch_ns']
        if (int(seq) != ordinal or Decimal(timestamp) * BILLION != epoch or
                (previous is None and delta != '') or
                (previous is not None and Decimal(delta) * BILLION != epoch - previous)):
            raise EvidenceError('Wireshark regression timestamps differ')
        previous = epoch
    if len(dhcp) != 4 or any(decoded[name] != dhcp for name in DHCP):
        raise EvidenceError('capture formats disagree on frame bytes or capture time')
    ntp = classic(tcp['tests/ntp-time.pcap'])
    actual = ntp_records(ntp)
    expected = []
    for line in tcp['tests/ntp-time.out'].decode().splitlines():
        match = re.fullmatch(r'\s*(\d+) +([\d-]+ [\d:.]+) IP .+: NTPv(\d+), (Client|Server), length (\d+)', line)
        if not match or int(match[1]) != len(expected) + 1:
            raise EvidenceError('invalid tcpdump expected record')
        since_epoch = datetime.fromisoformat(match[2]).replace(tzinfo=timezone.utc) - EPOCH
        epoch_ns = (since_epoch.days * 86400 + since_epoch.seconds) * BILLION + since_epoch.microseconds * 1000
        expected.append((epoch_ns, int(match[3]), match[4], int(match[5])))
    if len(ntp) != 2 or expected != actual or decoded[NTP] != [row for row, _ in ntp]:
        raise EvidenceError('tcpdump NTP baseline and decoded packets disagree')
    return {'dhcp': dhcp, 'ntp': decoded[NTP]}


def timeline(packets):
    sources = [{'source_id': name, 'clock_uncertainty_ms': 0} for name in packets]
    events = []
    for source, rows in packets.items():
        for index, row in enumerate(rows):
            micros, residual = divmod(row['epoch_ns'], 1000)
            if residual:
                raise EvidenceError('submicrosecond capture time exceeds timeline precision')
            events.append({'source_id': source, 'event_id': f'{source}-{index}', 'kind': 'network',
                           'sequence': index, 'parent_event_id': None, 'artifact_sha256': row['frame_sha256'],
                           'timestamp': (EPOCH + timedelta(microseconds=micros)).isoformat()})
    return forensic.analyze({'schema_version': 1, 'profile': 'normalized-evidence-timeline-v1',
                             'sources': sources, 'events': events})


def review_captures(source_root: Path):
    payloads, receipts = {}, {}
    for repo in SOURCES:
        payloads[repo], receipts[repo] = capture(source_root, repo, SOURCES, binary=True)
    wifi, tcp = payloads[WIRESHARK], payloads[TCPDUMP]
    shortened = tcp['tests/ntp-time.pcap'][:-4]
    with tempfile.TemporaryDirectory(prefix='nqc-offline-pcap-') as temp:
        path = Path(temp)
        for n in DHCP:
            (path / n).write_bytes(wifi['test/captures/' + n])
        (path / NTP).write_bytes(tcp['tests/' + NTP])
        (path / 'damaged-length.pcap').write_bytes(shortened)
        with ZipFile(path / 'vendor.zip', 'w') as archive:
            for name, data in payloads[SCAPY].items():
                archive.writestr(name, data)
        response = subprocess.run([*ISOLATE, sys.executable, '-I', '-S', '-B', worker.__file__],
                                  cwd=path, env={'HOME': temp, 'LANG': 'C'}, stdin=subprocess.DEVNULL,
                                  capture_output=True, check=True, timeout=20)
        decoded = strict_json(response.stdout)
    packets = check_data(decoded, wifi, tcp)
    if not any(row['captured'] != row['wire'] for row in decoded['damaged-length.pcap']):
        raise EvidenceError('short-packet control failed to expose capture loss')
    try:
        classic(shortened)
    except EvidenceError as exc:
        if str(exc) != 'truncated PCAP record or invalid length/time':
            raise
    else:
        raise EvidenceError('independent decoder accepted incomplete packet')
    good = timeline(packets)
    altered = timeline({**packets, 'ntp': list(reversed(packets['ntp']))})
    if (good['status'], good['event_count'], good['declared_edges'], altered['status'],
            len(altered['contradictions'])) != ('DECLARED_ORDER_CONSISTENT', 6, 4, 'DECLARED_CONSTRAINT_CONTRADICTION', 1):
        raise EvidenceError('forensic consumer failed chronology controls')
    results = {
        WIRESHARK: ('reference', 'verify_packet_and_timestamp_equivalence_across_four_file_formats',
                    {'formats': list(DHCP), 'frames': packets['dhcp']}),
        SCAPY: ('executed', 'decode_fixed_captures_into_the_NQC_forensic_timeline',
                {'frames_including_alternate_encodings': sum(len(decoded[n]) for n in (*DHCP, NTP)),
                 'unique_events_in_timeline': good['event_count'], 'declared_edges': good['declared_edges']}),
        TCPDUMP: ('reference', 'compare_capture_times_NTP_roles_and_lengths_with_tcpdump_oracle',
                  {'frames': packets['ntp'], 'modes': ['Client', 'Server'], 'NTP_version': 4}),
    }
    for repo, (role, operation, result) in results.items():
        receipts[repo].update({'role': role, 'operation': operation, 'result': result,
                               'timeline_sha256': sha(canonical(good)), 'timeline_status': good['status'],
                               'truncated_record_detected': True, 'reversed_order': altered['contradictions']})
    return receipts
