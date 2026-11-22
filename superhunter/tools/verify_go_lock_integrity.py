"""Verify checksums in root and v2 Go lockfiles against explicit local module proxies."""
import argparse
import base64
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile


GO_SHA = 'de0ae3e082ce7599eae4fb69fa2ef1e43b8f31ffd3fce62cdf81930aa9005050'
SOURCE_PATHS = ('go.mod', 'go.sum', 'v2/go.mod', 'v2/go.sum')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
    return subprocess.check_output(['git', '--no-replace-objects', '-c', 'submodule.recurse=false',
                                    '-C', root, *args], env=env)


def parse_git_tree(raw):
    rows = {}
    for line in raw.rstrip(b'\0').split(b'\0') if raw else []:
        meta, name = line.decode().split('\t', 1)
        rows[name] = meta.split()
    return rows


def object_id(kind, content):
    return hashlib.sha1(kind.encode() + b' ' + str(len(content)).encode() + b'\0' + content).hexdigest()


def locked(raw):
    entries = []
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        name, version, h1 = line.split()
        require(h1.startswith('h1:') and len(base64.b64decode(h1[3:], validate=True)) == 32, 'unsupported Go checksum')
        version, mod = (version[:-7], 'manifest') if version.endswith('/go.mod') else (version, 'archive')
        entries.append((name, version, mod, h1))
    require(len(entries) == len(set(entries)), 'duplicate lockfile row')
    return entries


def inspect_source(args):
    root, idx, name, relative, revision = args
    upstream = root / relative
    require(git(upstream, 'rev-parse', 'HEAD').decode().strip() == revision, 'checkout SHA mismatch')
    require(object_id('commit', git(upstream, 'cat-file', 'commit', revision)) == revision, 'commit object mismatch')
    raw = git(upstream, 'ls-tree', '-z', revision, '--', *SOURCE_PATHS)
    files = {}
    refs = []
    for path, (mode, typ, oid) in parse_git_tree(raw).items():
        require(mode in ('100644', '100755') and typ == 'blob', f'nonordinary selected path {name}/{path}')
        data = git(upstream, 'cat-file', 'blob', oid)
        require(object_id(typ, data) == oid and not (upstream/path).is_symlink() and (upstream/path).read_bytes() == data,
                f'working bytes diverge in {name}/{path}')
        files[path] = {'git_blob': oid, 'sha256': sha(data)}
        if path.endswith('go.sum'):
            refs.extend((path, row) for row in locked(data))
    row = {'id': idx, 'repository': name, 'revision': revision, 'selected_files': files}
    return row, refs


def gather(product, ref, checkouts):
    catalog_raw = git(product, 'show', f'{ref}:superhunter/repositories_200.json')
    catalog = json.loads(catalog_raw)['entries']
    entries = {row['id']: row['repository'] for row in catalog}
    urls = configparser.ConfigParser(interpolation=None)
    urls.read_string(git(product, 'show', f'{ref}:.gitmodules').decode())
    links = parse_git_tree(git(product, 'ls-tree', '-z', f'{ref}:upstream'))
    require(set(entries) == set(range(1,201)) and len(links) == len(catalog) == len(set(entries.values())) == 200,
            'expected exactly 200 distinct catalog identities')
    jobs = []
    for relative, (mode, typ, revision) in links.items():
        idx = int(relative.split('-', 1)[0])
        name = entries[idx]
        section = urls[f'submodule "upstream/{relative}"']
        require((mode, typ) == ('160000', 'commit') and section['path'] == 'upstream/' + relative and
                section['url'] == f'https://github.com/{name}.git', 'Gitlink mapping differs')
        jobs.append((checkouts, idx, name, relative, revision))
    require(len({job[1] for job in jobs}) == 200, 'repeated catalog ID')
    with ThreadPoolExecutor(max_workers=4) as workers:
        return list(workers.map(inspect_source, jobs)), sha(catalog_raw)


def unescape(path):
    require(re.fullmatch(r'(?:[^!]|![a-z])*', path) is not None, 'invalid case-escaped cache path')
    return re.sub(r'!([a-z])', lambda m:m[1].upper(), path)


def h1(line):
    return 'h1:' + base64.b64encode(hashlib.sha256(line).digest()).decode()


def hash_zip(path):
    lines = []
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        require(len(infos) <= 20_000 and sum(i.file_size for i in infos) <= 500 << 20, 'archive exceeds offline review limit')
        names = archive.namelist()
        require(len(names) == len(set(names)) and all('\n' not in n for n in names), 'ambiguous Go archive')
        for name in sorted(names):
            with archive.open(name) as src:
                digest = hashlib.file_digest(src, 'sha256').hexdigest()
            lines.append(f'{digest}  {name}\n'.encode())
    return h1(b''.join(lines))


def go_env(work, proxy, go):
    return {'HOME': str(work), 'PATH': '', 'GOROOT': str(go.parent.parent), 'GOTOOLCHAIN': 'local',
            'GOSUMDB': 'off', 'GOPROXY': proxy.as_uri(), 'GOMODCACHE': str(work/'modcache'),
            'GOCACHE': str(work/'buildcache'), 'GOWORK': 'off', 'GOENV': 'off', 'GOTELEMETRY': 'off',
            'CGO_ENABLED': '0', 'GOMAXPROCS': '2'}


def official_hashes(go, temp, cache, keys):
    if not keys:
        return {}
    with tempfile.TemporaryDirectory(dir=temp) as tmp:
        work = Path(tmp)
        (work/'go.mod').write_text('module example.invalid/offline-evidence\n\ngo 1.22.0\n')
        args = [str(go), 'mod', 'download', '-json', *(f'{m}@{v}' for m,v in sorted(keys))]
        result = subprocess.run(args, env=go_env(work,cache,go), cwd=work, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=240)
        require(result.returncode == 0, 'local Go reader failed: ' + result.stderr.decode()[-200:])
        text = result.stdout.decode().strip()
        values = {}
        decoder = json.JSONDecoder()
        while text:
            row, end = decoder.raw_decode(text)
            require('Error' not in row, 'local Go reader rejected an input')
            pair = row['Path'], row['Version']
            require(pair in keys and pair not in values, 'extra or repeated Go output')
            values[pair] = {'manifest': row['GoModSum'], 'archive': row['Sum']}
            text = text[end:].lstrip()
        require(keys == values.keys(), 'missing Go reader outputs')
        return values


def check_caches(pairs, specs, go, temp):
    inputs = {}
    input_receipts = []
    for label, cache in specs:
        available = {}
        for zpath in sorted(cache.glob('**/@v/*.zip')):
            mod_path = zpath.with_suffix('.mod')
            info_path = zpath.with_suffix('.info')
            require(all(f.is_file() and not f.is_symlink() and f.resolve().is_relative_to(cache)
                        for f in (zpath, mod_path, info_path)), 'incomplete or linked proxy tuple')
            name = unescape(zpath.parent.parent.relative_to(cache).as_posix())
            version = unescape(zpath.name[:-4])
            key = name, version
            if key not in pairs:
                continue
            require(key not in available, 'duplicate cache pair')
            meta = json.loads(info_path.read_bytes())
            require(meta['Version'] == version, 'cache version does not match its metadata')
            mod = mod_path.read_bytes()
            with zpath.open('rb') as src:
                zipsha = hashlib.file_digest(src, 'sha256').hexdigest()
            available[key] = {'manifest': h1(f'{sha(mod)}  go.mod\n'.encode()), 'archive': hash_zip(zpath)}
            input_receipts.append({'cache': label, 'module': name, 'version': version, 'zip_sha256': zipsha,
                                   'go_mod_sha256': sha(mod), 'info_sha256': sha(info_path.read_bytes()),
                                   'go_mod_h1':available[key]['manifest'], 'archive_h1':available[key]['archive']})
        checked = official_hashes(go, temp, cache, set(available))
        require(checked == available, f'Go and independent implementation disagree for {label}')
        for key, value in checked.items():
            require(key not in inputs or inputs[key] == value, 'local caches disagree')
            inputs[key] = value
    return inputs, input_receipts


def compare(sources, inputs):
    rows, unique, tallies, all_sums = [], set(), Counter(), defaultdict(set)
    for row, refs in sources:
        counts = Counter()
        for path, (name, version, kind, expected) in refs:
            key = name, version
            unique.add(key)
            all_sums[(name,version,kind)].add(expected)
            if key in inputs:
                state = 'matched' if inputs[key][kind] == expected else 'mismatched'
            else:
                state = 'unavailable_in_selected_caches'
            counts[f'{kind}_{state}'] += 1
        tallies.update(counts)
        rows.append({**row, 'checksum_lines': len(refs), 'outcomes': dict(sorted(counts.items()))})
    conflicts = {str(k): sorted(values) for k, values in all_sums.items() if len(values) > 1}
    return rows, unique, tallies, conflicts


def controls(go, temp):
    name, version = 'example.invalid/owned', 'v1.0.0'
    module_key = name, version
    with tempfile.TemporaryDirectory(dir=temp) as directory:
        root = Path(directory)
        proxy = root / 'proxy'
        versions = proxy / name / '@v'
        versions.mkdir(parents=True)
        mod = f'module {name}\n\ngo 1.22.0\n'.encode()
        (versions / (version+'.mod')).write_bytes(mod)
        (versions / (version+'.info')).write_text(json.dumps({'Version':version, 'Time':'2020-01-01T00:00:00Z'}))
        archive = versions / (version+'.zip')
        results = []
        for content, compression in [(b'one\n', zipfile.ZIP_STORED), (b'one\n', zipfile.ZIP_DEFLATED),
                                     (b'two\n', zipfile.ZIP_DEFLATED)]:
            with zipfile.ZipFile(archive, 'w', compression) as zf:
                zf.writestr(f'{name}@{version}/go.mod', mod)
                zf.writestr(f'{name}@{version}/README.txt', content)
            values = official_hashes(go, root, proxy, {module_key})[module_key]
            require(values['archive']==hash_zip(archive) and values['manifest']==h1(f'{sha(mod)}  go.mod\n'.encode()),
                    'fixture hash implementations disagree')
            results.append((sha(archive.read_bytes()),values))
        require(results[0][0]!=results[1][0] and results[0][1]==results[1][1], 'container compression changed content evidence')
        require(results[1][1]['archive']!=results[2][1]['archive'] and results[1][1]['manifest']==results[2][1]['manifest'],
                'changed member failed to invalidate the archive')
        observations = [(name,version,'archive',results[1][1]['archive']), (name,version,'manifest',results[1][1]['manifest'])]
        _,_,counts,_ = compare([({'id':1}, [('go.sum',r) for r in observations])], {module_key:results[2][1]})
        require(counts=={'archive_mismatched':1,'manifest_matched':1}, 'a stale archive checksum was credited')
        return {'recompressed_container_keeps_content_checksum':True, 'changed_archive_member_invalidates_checksum':True,
                'stale_archive_checksum_refuted_with_unchanged_manifest':True}


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--product', type=Path, required=True)
    args.add_argument('--revision', required=True)
    args.add_argument('--checkouts', type=Path, required=True)
    args.add_argument('--cache', action='append', required=True, metavar='LABEL=DOWNLOAD_ROOT')
    args.add_argument('--go', type=Path, required=True)
    args.add_argument('--temp', type=Path, required=True)
    opt = args.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', opt.revision), 'full public product revision required')
    go = opt.go.resolve(strict=True)
    require(sha(go.read_bytes()) == GO_SHA, 'Go reader differs from product pin')
    specs = [(v.split('=',1)[0], Path(v.split('=',1)[1]).resolve(strict=True)) for v in opt.cache]
    labels = [k for k,_ in specs]
    require(len(labels) == len(set(labels)) and all(re.fullmatch(r'[a-z0-9-]+', v) for v in labels), 'bad cache labels')
    sources, catalog_sha = gather(opt.product, opt.revision, opt.checkouts)
    pairs = {(m,v) for row,refs in sources for path,(m,v,kind,checksum) in refs}
    inputs, receipts = check_caches(pairs, specs, go, opt.temp.resolve(strict=True))
    rows, unique, tallies, conflicts = compare(sources, inputs)
    require(pairs == unique and sum(tallies.values()) == sum(r['checksum_lines'] for r in rows), 'census counts differ')
    checked_rows = [r for r in rows if r['selected_files']]
    result = {'schema_version': 1, 'scope': 'Root and v2 Go manifests and checksum files at all 200 catalog commits. '
              'Both Go and an independent implementation hashed available module archives and manifests. '
              'The selected previously staged local proxy snapshots bound content availability. No public checksum '
              'database, execution, resolved dependency graph, licensing decision or integration coverage is asserted.',
              'producer': opt.revision, 'catalog_sha256': catalog_sha, 'catalog_upstream_tree':
              git(opt.product,'rev-parse',opt.revision+':upstream').decode().strip(), 'go_reader_sha256':GO_SHA,
              'selected_paths': SOURCE_PATHS, 'cache_labels': labels, 'total_catalog': len(rows),
              'repositories_with_selected_files':len(checked_rows), 'repositories_with_go_sum':
              sum(any(p.endswith('go.sum') for p in r['selected_files']) for r in rows),
              'repositories_with_at_least_one_matched_checksum':sum(any(k.endswith('_matched') for k in r['outcomes']) for r in rows),
              'distinct_module_versions_in_locks':len(pairs), 'independently_recomputed_module_versions':len(inputs),
              'checksum_lines':sum(tallies.values()), 'line_outcomes':dict(sorted(tallies.items())),
              'controls':controls(go,opt.temp.resolve(strict=True)), 'conflicting_lockfile_claims':conflicts, 'verified_cache_inputs':receipts, 'repositories_with_selected_paths':checked_rows,
              'ids_without_selected_paths':[r['id'] for r in rows if not r['selected_files']]}
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__ == '__main__':
    main()
