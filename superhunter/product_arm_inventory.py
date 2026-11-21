"""Replay NQC's fixed manifest inventory with the ARM64 Syft release under QEMU user mode."""
from collections import Counter
from pathlib import Path
import subprocess
import tempfile

from .product_reasoning import EvidenceError, INPUTS, observed_facts
from .product_review import SYFT_SCAN, capture_inputs, copy_release, sha, stage_inputs
from .safe_io import canonical

QEMU_SHA = '73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943'
SYFT_ARM_SHA = '69d1bb01433f170f360fb208f7320e988182aaa7d2b1928c3ade9802993eebd8'


def assess(sbom, product):
    facts = sorted((INPUTS[path], name, version) for path, name, version in observed_facts(sbom))
    expected = sorted((p['source'], p['name'], p['version']) for p in product['packages'])
    if not facts or facts != expected:
        raise EvidenceError('ARM64 inventory differs from the verified native Syft inventory')
    return {'observations': len(facts), 'by_source': dict(Counter(row[0] for row in facts)),
            'facts_sha256': sha(canonical(facts))}


def build(qemu, syft, product):
    inputs = capture_inputs()
    if any(sha(raw) != product['input_sha256'][INPUTS[path]] for path, raw in inputs.items()):
        raise EvidenceError('manifest inputs changed before ARM64 inventory')
    with tempfile.TemporaryDirectory(prefix='nqc-arm-inventory-') as temp:
        work = Path(temp)
        copy_release('QEMU user', qemu, work/'qemu-aarch64', QEMU_SHA)
        copy_release('Syft ARM64', syft, work/'syft-arm64', SYFT_ARM_SHA)
        stage_inputs(work, inputs)
        sbom = subprocess.check_output(['/usr/bin/unshare', '--user', '--map-current-user', '--net',
                                       str(work/'qemu-aarch64'), str(work/'syft-arm64'), *SYFT_SCAN],
                                      cwd=work, env={'HOME': temp, 'XDG_CONFIG_HOME': temp, 'LC_ALL': 'C',
                                                     'SYFT_CHECK_FOR_APP_UPDATE': 'false', 'GOMAXPROCS': '2'},
                                      stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
    return {**assess(sbom, product), 'architecture': 'aarch64', 'qemu_version': '10.0.13',
            'qemu_sha256': QEMU_SHA, 'syft_version': '1.38.2', 'syft_arm64_sha256': SYFT_ARM_SHA}
