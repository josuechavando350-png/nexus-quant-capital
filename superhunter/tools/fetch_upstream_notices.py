"""Download the fixed set of GitHub license artifacts for offline query-product sessions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from superhunter.product_upstream_notices import filename, select_document, sources
from superhunter.safe_io import write_new_bundle


def fetch(row):
    notice = row['notice']
    url = f"https://raw.githubusercontent.com/{row['repository']}/{row['revision']}/{quote(notice['path'])}"
    with urlopen(url, timeout=45) as response:
        raw = response.read(notice['bytes'] + 1)
    return filename(row), select_document(row, raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new directory for verified notices')
    folder = parser.parse_args().output
    if folder.exists():
        parser.error('output already exists')
    with ThreadPoolExecutor(max_workers=6) as pool:
        docs = dict(pool.map(fetch, sources()))
    write_new_bundle(folder, docs)
    print(f'{len(docs)} upstream notices verified')


if __name__ == '__main__':
    main()
