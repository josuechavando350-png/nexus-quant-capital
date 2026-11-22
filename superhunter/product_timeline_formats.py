"""Compare timestamp codecs against the normalized fixture of NQC's two-source journal correlator."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from . import forensic_timeline as forensic
from .product_infra_batch import capture
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import canonical, read_artifact, strict_json

JAEGER = 'jaegertracing/jaeger'
HUBBLE = 'cilium/hubble'
FALCO = 'falcosecurity/falco'
SOURCES = {
    JAEGER: ('048-jaeger', 'f9046f3dadd6778e0b2995bc6b41fdf35f9381b1', ('internal/jptrace/timestamp.go',)),
    HUBBLE: ('089-hubble', '35bf8033a880ac9b04bd0499067615de4815585b', ('vendor/github.com/cilium/cilium/hubble/pkg/time/time.go',)),
    FALCO: ('086-falco', '74ccf76b7b2d85ff42c97da6bd6a716b0d1d17b9', ('userspace/engine/formats.cpp',)),
}
GO_SHA = 'de0ae3e082ce7599eae4fb69fa2ef1e43b8f31ffd3fce62cdf81930aa9005050'
RUNNER_SHA = '673d1d0fea66e0e4be03867810b2c46c699c1df2d099711d29ffe03d3c8a0f39'
FIXTURE = 'superhunter/product_supply/infra_batch_journal_fixture.json'
DRIVER = 'superhunter/product_supply/infra_batch_clock_driver.txt'
FIXTURE_SHA = '2c8b77128993fb9f97c04841f78225afdb25c4e0c247748114de189b8d15645c'
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def sources(source_root):
    files, evidence = {}, {}
    for name in SOURCES:
        data, evidence[name] = capture(source_root, name, SOURCES, binary=True)
        files[name], = data.values()
    return files, evidence


def build(work, go, files, output):
    go = go.resolve(strict=True)
    with go.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != GO_SHA:
            raise EvidenceError('timeline Go compiler differs')
    for name, repo in [('jaeger', JAEGER), ('hubble', HUBBLE)]:
        package = work / name
        package.mkdir()
        (package / 'time.go').write_bytes(files[repo])
    (work / 'main.go').write_bytes(read_artifact(ROOT, DRIVER))
    (work / 'go.mod').write_text('module nqc.local/clocks\n\ngo 1.27\n')
    env = {'HOME': str(work), 'PATH': str(go.parent), 'GOENV': 'off', 'GOWORK': 'off', 'GOPROXY': 'off',
           'GOSUMDB': 'off', 'GOTOOLCHAIN': 'local', 'CGO_ENABLED': '0', 'GOTELEMETRY': 'off',
           'GOROOT': str(go.parent.parent), 'GOCACHE': str(work/'cache'), 'GOPATH': str(work/'gopath'),
           'GOOS': 'linux', 'GOARCH': 'amd64', 'GOMAXPROCS': '2'}
    subprocess.run([*ISOLATE, go, 'build', '-p=2', '-trimpath', '-buildvcs=false', '-ldflags=-buildid=',
                    '-o', output, '.'], cwd=work, env=env, check=True, capture_output=True, timeout=150)


def format_rules(raw):
    # Read the formatting and resolution used by the normal Falco event JSON
    # serializer. The resulting strings are projections, not Falco detections.
    source = raw.decode()
    whole, = re.findall(r'time_t evttime = evt->get_ts\(\) / (\d+);', source)
    fraction, = re.findall(r'snprintf\(time_ns, sizeof\(time_ns\), "\.%(\d+)luZ", evt->get_ts\(\) % (\d+)\);', source)
    fmt, = re.findall(r'strftime\(time_sec, sizeof\(time_sec\), "([^"]+)", &tm_buf\);', source)
    width, remainder = map(int, fraction)
    if int(whole) != 10 ** width or int(remainder) != int(whole) or fmt != '%FT%T':
        raise EvidenceError('unsupported Falco timestamp resolution')
    return fmt, width, int(whole)


def encode_falco(value, layout):
    fmt, decimals, base = layout
    delta = datetime.fromisoformat(value) - EPOCH
    micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    nanos = micros * 1000
    sec, frac = divmod(nanos, base)
    instant = datetime.fromtimestamp(sec, timezone.utc).strftime(fmt)
    return f'{instant}.{frac:0{decimals}d}Z', nanos


def verify_times(events, native, labels, expected_ns):
    if len(native) != len(labels):
        raise EvidenceError('timeline codec response count differs')
    for index, event in enumerate(events):
        n = expected_ns[index]
        # Each original timestamp and its derived Falco representation carry
        # equal instants in two independent upstream decodings.
        first, second = native[2 * index:2 * index + 2]
        if (not first['Valid'] or first != second or first['Nanos'] != n
                or datetime.fromisoformat(first['RoundTrip']) != datetime.fromisoformat(event['timestamp'])):
            raise EvidenceError('journal timestamp not conserved through both codecs')
    invalid, zero, before, extra = native[-4:]
    if invalid['Valid'] or not all(r['Valid'] and r['Nanos'] == 0 for r in (zero, before)):
        raise EvidenceError('invalid or missing timestamp controls disagree')
    if (extra['Nanos'] != native[0]['Nanos'] + 1 or
            extra['Millis'] != native[0]['Millis'] or extra['RoundTrip'] == native[0]['RoundTrip']):
        raise EvidenceError('submillisecond precision collision was not detected')


def review(source_root: Path):
    files, evidence = sources(source_root)
    raw = read_artifact(ROOT, FIXTURE)
    if sha(raw) != FIXTURE_SHA:
        raise EvidenceError('journal fixture projection changed')
    fixture = strict_json(raw)
    events = fixture['events']
    timeline = forensic.analyze(fixture)
    ns, labels = [], []
    layout = format_rules(files[FALCO])
    for event in events:
        formatted, epoch = encode_falco(event['timestamp'], layout)
        ns.append(epoch)
        labels.extend([event['timestamp'], formatted])
    # Increment the final nanosecond of the actual first event as a precision control.
    if not labels[1].endswith('000Z'):
        raise EvidenceError('journal precision control needs an exact microsecond')
    probe = labels[1][:-2] + '1Z'
    labels.extend(['unrecognized-time', '1970-01-01T00:00:00Z', '1969-12-31T23:59:59Z', probe])
    with tempfile.TemporaryDirectory(prefix='nqc-journal-formats-') as tmp:
        work = Path(tmp)
        exe = work / 'clocks'
        kit = os.environ.get('NQC_TIMELINE_RUNNER')
        if kit:
            copy_release('journal clock adapter', Path(kit), exe, RUNNER_SHA)
        else:
            build(work, Path(os.environ.get('NQC_STATE_GO', '/no-state-go')), files, exe)
            if sha(exe.read_bytes()) != RUNNER_SHA:
                raise EvidenceError('clock adapter binary differs from reproducible build')
        p = subprocess.run([*ISOLATE, exe], input=canonical(labels), cwd=work, env={'TZ': 'UTC'},
                           check=True, capture_output=True, timeout=10)
    native = json.loads(p.stdout)
    verify_times(events, native, labels, ns)
    identities = {(e['source_id'], e['sequence']): e['artifact_sha256'] for e in events}
    if (len(identities), len({e['sequence'] for e in events}), timeline['declared_edges']) != (4, 2, 2):
        raise EvidenceError('unexpected cross-source sequence collisions')
    merged = deepcopy(fixture)
    merged['events'][2]['source_id'] = events[0]['source_id']
    try:
        forensic.analyze(merged)
    except forensic.TimelineError as exc:
        if str(exc) != 'DUPLICATE_SOURCE_SEQUENCE':
            raise
    else:
        raise EvidenceError('merged journal sources accepted')
    common = {'fixture_sha256': sha(raw), 'events': len(events), 'sources': len(fixture['sources']),
              'timeline_sha256': sha(canonical(timeline)), 'source_erasure_control': 'DUPLICATE_SOURCE_SEQUENCE'}
    evidence[JAEGER].update(common, role='executed', operation='convert_and_reverse_epoch_nanoseconds',
                            epochs_ns=ns, zero_and_pre_epoch_sentinel=0, clock_runner_sha256=RUNNER_SHA)
    evidence[HUBBLE].update(common, role='executed', operation='parse_absolute_times_and_measure_format_precision_loss',
                            millisecond_collision=native[0]['Millis'], nanosecond_control=native[-1]['RoundTrip'],
                            malformed_timestamp_rejected=True, clock_runner_sha256=RUNNER_SHA)
    evidence[FALCO].update(common, role='reference', operation='apply_event_JSON_timestamp_resolution',
                           fraction_digits=layout[1], unit_per_second=layout[2], labels=labels[1:8:2])
    return evidence
