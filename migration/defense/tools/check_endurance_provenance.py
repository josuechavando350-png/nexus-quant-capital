"""Check recorded endurance reports against immutable local Git objects; never rerun or certify time."""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import subprocess


def require(condition, reason):
    if not condition: raise ValueError(reason)


def hex_value(value, length):
    require(isinstance(value,str) and re.fullmatch('[0-9a-f]{'+str(length)+'}',value),'provenance_digest')
    return value


def source_path(name):
    require(isinstance(name,str),'provenance_source_path')
    if name.startswith('harness:'): name='tools/'+name.removeprefix('harness:')
    elif '/' not in name: name='nqc_defense/'+name
    require(re.fullmatch(r'(nqc_defense|tools)/[a-zA-Z0-9_]+\.py',name),'provenance_source_path')
    return 'migration/defense/'+name


def git_bytes(repo, commit, path):
    hex_value(commit,40)
    require(re.fullmatch(r'migration/defense/(nqc_defense|tools)/[a-zA-Z0-9_]+\.py',path),'provenance_git_path')
    args=['git','--no-replace-objects','-C',str(repo)]
    size=subprocess.check_output(args+['cat-file','-s',commit+':'+path],stderr=subprocess.DEVNULL,timeout=5)
    require(0<int(size)<=2*1024*1024,'provenance_source_size')
    data=subprocess.check_output(args+['show',commit+':'+path],stderr=subprocess.DEVNULL,timeout=5)
    require(len(data)==int(size),'provenance_source_size')
    return data


def verify(index, repo, package, *, require_complete=False):
    require(type(index) is dict and index.get('schema')=='nqc-endurance-provenance-v1','provenance_schema')
    reports=index.get('reports'); pending=index.get('other_runs_in_progress')
    require(type(reports) is list and 1<=len(reports)<=16,'provenance_report_count')
    require(type(pending) is list and len(pending)<=16 and all(isinstance(x,str) and len(x)<=256 for x in pending),'provenance_pending')
    require(not require_complete or not pending,'provenance_runs_pending')
    output=[]; seen=set()
    for entry in reports:
        require(type(entry) is dict,'provenance_entry')
        name=entry.get('path'); require(isinstance(name,str) and re.fullmatch(r'docs/[A-Z0-9_]+\.json',name),'provenance_report_path')
        require(name not in seen,'provenance_duplicate_report'); seen.add(name)
        path=Path(package)/name; info=path.lstat()
        require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_size<=2*1024*1024,'provenance_report_file')
        raw=path.read_bytes(); require(hashlib.sha256(raw).hexdigest()==hex_value(entry.get('sha256'),64),'provenance_report_digest')
        report=json.loads(raw)
        require(type(report) is dict,'provenance_report_shape')
        require(report.get('verified') is True and report.get('source_unchanged_at_finish') is True and report.get('failures')==[],'provenance_run_failed')
        requested=report.get('requested_seconds'); elapsed=report.get('elapsed_seconds')
        require(type(requested) is int and 1<=requested<=86400,'provenance_requested_duration')
        require(type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed>=requested,'provenance_incomplete_duration')
        require(entry.get('requested_seconds')==requested and entry.get('completed_seconds')==elapsed,'provenance_duration_disagrees')
        commit=hex_value(entry.get('tested_runtime_commit'),40)
        sources=report.get('source_sha256'); require(type(sources) is dict and 1<=len(sources)<=16,'provenance_sources')
        schema=report.get('schema')
        if schema=='nqc-registry-endurance-v1':
            expected={'nqc_defense/signer_registry.py','nqc_defense/dossier_attestation.py',
                      'tools/check_signer_registry.py','tools/soak_signer_registry.py'}
        elif schema=='nqc-mirror-endurance-v2':
            expected={'__init__.py','dossier_attestation.py','registry_mirror.py','signer_registry.py',
                      'sqlite_limits.py','harness:soak_registry_mirror.py'}
            require(report.get('tested_package_version')==entry.get('tested_runtime_version'),'provenance_report_version')
        elif 'schema' not in report:
            require(entry.get('tested_runtime_version')=='0.20.0','provenance_version')
            expected={'dossier_attestation.py','registry_mirror.py','signer_registry.py'}
        else:
            raise ValueError('provenance_run_schema')
        require(set(sources)==expected,'provenance_source_membership')
        for source,digest in sources.items():
            data=git_bytes(repo,commit,source_path(source))
            require(hashlib.sha256(data).hexdigest()==hex_value(digest,64),'provenance_source_digest')
        init=ast.parse(git_bytes(repo,commit,'migration/defense/nqc_defense/__init__.py'))
        versions=[ast.literal_eval(n.value) for n in init.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets)]
        require(versions==[entry.get('tested_runtime_version')],'provenance_version')
        if 'tested_package_version' in report: require(report['tested_package_version']==versions[0],'provenance_report_version')
        registry=report.get('schema')=='nqc-registry-endurance-v1'
        harness='tools/soak_signer_registry.py' if registry else 'tools/soak_registry_mirror.py'
        harness_data=git_bytes(repo,entry.get('harness_preserved_in_commit'),'migration/defense/'+harness)
        require(hashlib.sha256(harness_data).hexdigest()==hex_value(entry.get('harness_sha256'),64),'provenance_harness_digest')
        calls=report.get('records_registered_and_publicly_verified') if registry else report.get('verified_calls')
        require(type(calls) is int and calls>0,'provenance_operation_count')
        harness_reported=any(source_path(name)=='migration/defense/'+harness for name in sources)
        output.append({'report':name,'runtime_commit':commit,'runtime_version':versions[0],
            'elapsed_seconds':elapsed,'verified_operations':calls,'matched_source_files':len(sources),
            'harness_hash_recorded_in_run':harness_reported,'verified':True})
    return {'verified':True,'reports':output,'pending_run_descriptions':pending,
            'all_recorded_runs_complete':not pending,'local_git_objects_checked':True,
            'independent_execution_attestation':False,'wall_clock_independently_certified':False,
            'production_performance_claimed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument('--require-complete',action='store_true'); args=parser.parse_args()
    package=args.repo/'migration/defense'
    try:
        index=json.loads((package/'docs/ENDURANCE_PROVENANCE.json').read_text())
        print(json.dumps(verify(index,args.repo,package,require_complete=args.require_complete),indent=2,sort_keys=True)); return 0
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print(json.dumps({'verified':False,'reason':str(exc) if type(exc) is ValueError else 'local_provenance_error'})); return 2


if __name__=='__main__':
    raise SystemExit(main())
