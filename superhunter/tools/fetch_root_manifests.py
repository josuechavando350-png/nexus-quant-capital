"""Prepare just the reviewed, non-executable root manifests at their immutable revisions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

from superhunter.product_remote_roots import manifests, member_name, roots
from superhunter.repository_boundary import git_object
from superhunter.safe_io import MAX_BYTES, write_new_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    def fetch(item):
        row, name, oid = item
        url = f"https://raw.githubusercontent.com/{row['repository']}/{row['commit']}/{name}"
        with urlopen(url, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or git_object('blob', raw) != oid:
            raise ValueError('manifest does not match the pinned Git blob')
        return member_name(row['id'], name), raw
    items = [(row, name, oid) for row, tree in roots() for name, oid in manifests(tree).items()]
    with ThreadPoolExecutor(max_workers=5) as pool:
        files = dict(pool.map(fetch, items))
    write_new_bundle(args.destination, files)
    print(f'{len(files)} verified dependency manifests')


if __name__ == '__main__':
    main()
