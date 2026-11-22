"""Exercise the read-only product CLI over a live pipe, including a clean restart."""
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

from superhunter.product_review import ROOT
from superhunter.safe_io import canonical, strict_json
from superhunter.tools.verify_source_materialization import expected_rows


async def exchange(process, key, timeout):
    process.stdin.write((key + '\n').encode())
    await asyncio.wait_for(process.stdin.drain(), timeout)
    line = await asyncio.wait_for(process.stdout.readline(), timeout)
    if not line.endswith(b'\n'):
        raise ValueError('missing complete response for ' + key)
    if line == b'null\n':
        return None
    return strict_json(line)


def check_identity(reply, pin):
    source = reply['source_inventory']
    identity = reply['github_identity']
    if ((reply['catalog_id'], reply['repository'], source['revision'], source['tree'])
            != (pin['catalog_id'], pin['repository'], pin['commit'], pin['tree'])
            or (source['id'], source['repository']) != (reply['catalog_id'], reply['repository'])
            or (identity['id'], identity['full_name'], identity['github_id'])
            != (source['id'], source['repository'], source['github_id'])):
        raise ValueError('reply differs from the pinned identity: ' + pin['repository'])


async def session(workspace, pins):
    command = ['/usr/bin/unshare', '--user', '--map-current-user', '--net', '--pid',
               '--fork', '--kill-child', sys.executable, '-B', '-m', 'superhunter', 'query-product',
               '--bundle', workspace/'product', '--supply', workspace/'supply',
               '--notice-wheels', workspace/'supply-wheels', '--source-inventory',
               '--qdrant', workspace/'qdrant', '--haystack-wheels', workspace/'haystack']
    proc = await asyncio.create_subprocess_exec(*command, cwd=ROOT, stdin=asyncio.subprocess.PIPE,
                                                stdout=asyncio.subprocess.PIPE, limit=4 * 1024**2)
    try:
        # Startup includes validation and an offline installation of hash-pinned wheels.
        if await exchange(proc, 'nqc-unknown-catalog-entry', 240) is not None:
            raise ValueError('unknown key returned a catalog entry')
        replies = {}
        for pin in pins:
            reply = await exchange(proc, pin['repository'], 20)
            check_identity(reply, pin)
            replies[pin['repository']] = sha256(canonical(reply)).hexdigest()
        search = await exchange(proc, 'notice:redistribution', 60)
        if (search['terms'] != ['redistribution'] or not search['matches']
                or any('bm25_score' not in hit for hit in search['matches'])):
            raise ValueError('missing reconciled Qdrant and Haystack notice results')
        proc.stdin.close()
        await proc.stdin.wait_closed()
        if await asyncio.wait_for(proc.stdout.read(1), 60) or await asyncio.wait_for(proc.wait(), 20):
            raise ValueError('extra output or unsuccessful product shutdown')
        return {'repositories': len(replies), 'identity_responses_sha256': sha256(canonical(replies)).hexdigest(),
                'notice_matches': len(search['matches']), 'notice_response_sha256': sha256(canonical(search)).hexdigest(),
                'unknown_key_returned_null': True, 'exit_code': proc.returncode}
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def verify(workspace):
    pins = expected_rows()
    first = await session(workspace, pins)
    second = await session(workspace, reversed(pins))
    if first != second:
        raise ValueError('responses differ after restarting the product')
    return {'transport': 'local stdio', 'first': first, 'after_clean_restart': second}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('workspace', nargs='?', type=Path, help='prepared catalog workspace')
    inputs.add_argument('--prepare', action='store_true', help='acquire pinned inputs and build fresh bundles')
    args = parser.parse_args()
    if args.prepare:
        from superhunter.tools.catalog_session import prepare
        with tempfile.TemporaryDirectory(prefix='nqc-catalog-') as temp:
            workspace = Path(temp)
            prepare(workspace, transport_only=True)
            result = asyncio.run(verify(workspace))
    else:
        result = asyncio.run(verify(args.workspace.resolve()))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
