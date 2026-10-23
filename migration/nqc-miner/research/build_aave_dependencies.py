#!/usr/bin/env python3
"""Recompile unchanged dependency sources using checksum-pinned local solc files."""
import argparse
import gzip
from pathlib import Path
import audit_aave_dependencies as audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit.probe.check(not any(p.is_symlink() for p in (args.output, *args.output.parents)), 'output symlink')
    args.output.mkdir(parents=True, exist_ok=False)
    profiles, inputs, _ = audit.retained_inputs()
    for p in profiles:
        address = p['address']; version = p['compiler_version'].split('+')[0]
        raw, stderr = audit.compile_source(args.compiler_directory / ('solc-' + version), inputs[address], p)
        audit.probe.check(audit.probe.sha(raw) == p['compiler_output_sha256'], 'recompiled output mismatch')
        for suffix, data in [('input.json.gz', audit.ENCODE(inputs[address])), ('output.json.gz', raw)]:
            (args.output / (address + '-' + suffix)).write_bytes(gzip.compress(data, mtime=0))
        (args.output / (address + '.stderr')).write_bytes(stderr)
        print(address + ': reproduced exact compiler output')


if __name__ == '__main__':
    main()
