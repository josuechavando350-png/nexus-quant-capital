"""Read only public GitHub identity metadata and optional pinned commit records."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from urllib.request import Request, urlopen

from superhunter.product_review import ROOT, sha
from superhunter.product_source_audit import REMOTE, REMOTE_SHA
from superhunter.product_upstream_notices import sources
from superhunter.safe_io import canonical, read_artifact, strict_json


class RepoHead(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self.finished = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        name = attrs.get('name', '')
        if tag == 'meta' and name in ('octolytics-dimension-repository_id', 'octolytics-dimension-repository_nwo'):
            if name in self.fields:
                raise ValueError('ambiguous GitHub repository identity')
            self.fields[name] = attrs.get('content')

    def handle_endtag(self, tag):
        if tag == 'head':
            self.finished = True


def get_identity(row):
    request = Request('https://github.com/' + row['repository'], headers={'User-Agent': 'NQC-source-provenance'})
    parser = RepoHead()
    with urlopen(request, timeout=30) as response:
        for _ in range(48):
            data = response.read(8192)
            if not data:
                break
            parser.feed(data.decode('latin1'))
            if parser.finished:
                break
    fields = parser.fields
    if (fields.get('octolytics-dimension-repository_id') != str(row['github_id'])
            or fields.get('octolytics-dimension-repository_nwo') != row['repository']):
        raise ValueError('GitHub identity differs for catalog ID ' + str(row['id']))
    return {'id': row['id'], 'name': row['repository'], 'github_id': row['github_id']}


def get_commit(row):
    with urlopen(row['url'], timeout=30) as response:
        record = strict_json(response.read(2_000_001))
    if record['sha'] != row['commit'] or record['tree']['sha'] != row['tree']:
        raise ValueError('GitHub commit differs for catalog ID ' + str(row['id']))
    return row['id']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remote-trees', action='store_true', help='also check the 47 catalog-only commit records')
    args = parser.parse_args()
    rows = sources()
    with ThreadPoolExecutor(max_workers=5) as pool:
        identities = list(pool.map(get_identity, rows))
        result = {'identities': len(identities), 'identity_rows_sha256': sha(canonical(identities))}
        if args.remote_trees:
            data = read_artifact(ROOT, REMOTE)
            if sha(data) != REMOTE_SHA:
                raise ValueError('remote commit receipt differs')
            ids = list(pool.map(get_commit, strict_json(data)['commits']))
            result['remote_trees'] = len(ids)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
