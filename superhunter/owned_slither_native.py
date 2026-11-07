"""Evaluate/replay three fixed own Slither controls with original JSON preserved.

The generic external-report importer remains strict. A separate, explicit
conversion represents Slither's successful empty-results encoding and binds
both byte sequences. Detector expectations are not contract-security proofs.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from . import quality, native_platform, native_compile, owned_process, static_review
from . import slither_owned_runner as prior, slither_control_pair as pair
from . import owned_slither_dependencies as dependencies, owned_slither_network as network
from . import owned_slither_cases as fixture_cases
from .owned_slither_cases import SOURCES, WORKER_POLICY, FIXTURE_COMMIT, context
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-slither-three-control-native-v2'
CAPTURE_FILES = {'slither-original.json','source.sol','admission.json','execution.json','stdout.log','stderr.log'}
CONVERSION_FILES = {'slither-normalized.json','conversion.json','context.json'}
REVIEW_FILES = {'evaluation.json','REVIEW.md'}
need,sha = dependencies.need,dependencies.sha


def source_identity(expected: str) -> dict:
    fixture_cases.fixture_provenance()
    snapshot = quality.source_snapshot()
    need(type(expected) is str and sha(canonical(snapshot))==expected,'OWNED_SLITHER_SOURCE_IDENTITY')
    return snapshot


def convert_original(raw: bytes, mode: str) -> tuple[bytes,dict]:
    need(mode in SOURCES and type(raw) is bytes and len(raw)<=2_000_000,'OWNED_SLITHER_CONVERSION_INPUT')
    report = strict_json(raw)
    need(set(report)=={'success','error','results'} and report['success'] is True and
         report['error'] is None and type(report['results']) is dict,'OWNED_SLITHER_REPORT_FAILED')
    results = report['results']
    if results=={}:
        normalized = canonical({'success':True,'error':None,'results':{'detectors':[]}})
        rule = 'successful-empty-results-to-explicit-empty-detector-list'
    else:
        need(set(results)=={'detectors'} and type(results['detectors']) is list,
             'OWNED_SLITHER_REPORT_SECTIONS')
        normalized,rule = raw,'explicit-detector-list-unchanged'
    return normalized,{'schema_version':1,'rule':rule,'mode':mode,
                       'original_sha256':sha(raw),'normalized_sha256':sha(normalized),
                       'original_bytes_preserved':True,'producer_authenticated':False}


def _manifest(root: Path, files: set[str]) -> dict:
    marker = strict_json(read_artifact(root,'COMPLETE.json'))
    need(set(marker)=={'schema_version','sha256'} and type(marker['schema_version']) is int and
         marker['schema_version']==1 and type(marker['sha256']) is dict and
         set(marker['sha256'])==files,'OWNED_SLITHER_MANIFEST')
    hashes = native_platform._tree(root,files|{'COMPLETE.json'})
    need(all(hashes[name]==marker['sha256'][name] for name in files),'OWNED_SLITHER_MANIFEST_BYTES')
    return hashes


def _admission(mode: str, expected: str) -> dict:
    return {'schema_version':1,'mode':mode,'source_digest':expected,'source_sha256':sha(SOURCES[mode]),
            'fixture_provenance':fixture_cases.fixture_provenance(),
            'dependencies':dependencies.expected_identity(),'network':network.expected_proof(),
            'worker_policy':WORKER_POLICY}


def _run_case(mode: str, out: Path, image: bytes, expected: str) -> None:
    out.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix='owned-slither-native-') as temp:
        work = Path(temp)
        prior._write_local(work/'Owned.sol',SOURCES[mode],0o400)
        prior._write_local(work/'solc',image,0o500)
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
            command = [sys.executable,'-I','-B','-X','pycache_prefix='+str(work/'launcher-cache'),
                       str(ROOT/'owned_slither_native_worker.py'),str(work),mode,expected]
            try:
                proc = owned_process.run(command,cwd=work,
                    env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','HOME':str(work),'PATH':'/usr/bin:/bin'},
                    timeout=WORKER_POLICY['wall_seconds'],stdout=output,stderr=errors)
                returncode = proc.returncode
                timed_out = False
            except subprocess.TimeoutExpired:
                returncode,timed_out = None,True
            output.seek(0);errors.seek(0)
            stdout,stderr = output.read(2_000_001),errors.read(2_000_001)
            need(len(stdout)<=2_000_000 and len(stderr)<=2_000_000,'OWNED_SLITHER_OUTPUT_BUDGET')
        found = {}
        for name in ('slither.json','admission.json'):
            found[name] = read_artifact(work,name) if (work/name).exists() else None
        record = {'schema_version':1,'mode':mode,'source_digest':expected,'returncode':returncode,'timed_out':timed_out,
                  'report_present':found['slither.json'] is not None,
                  'admission_present':found['admission.json'] is not None}
        write_new_bundle(out/'capture',{'slither-original.json':found['slither.json'] or b'',
            'source.sol':SOURCES[mode],'admission.json':found['admission.json'] or b'',
            'execution.json':canonical(record),'stdout.log':stdout,'stderr.log':stderr})
        need(type(returncode) is int and returncode==0 and not timed_out and
             all(value is not None for value in found.values()),'OWNED_SLITHER_WORKER_FAILED')
        need(found['admission.json']==canonical(_admission(mode,expected)),'OWNED_SLITHER_ADMISSION')
        need(read_artifact(work,'Owned.sol')==SOURCES[mode] and
             native_compile.read_pinned_binary(work/'solc')==image,'OWNED_SLITHER_INPUT_CHANGED')
        normalized,conversion = convert_original(found['slither.json'],mode)
        ctx = context(mode,sha(normalized))
        write_new_bundle(out/'conversion',{'slither-normalized.json':normalized,
            'conversion.json':canonical(conversion),'context.json':canonical(ctx)})
        static_review.import_report(out/'conversion/slither-normalized.json',
                                    out/'conversion/context.json',work,out/'imported')


def _observe(root: Path, mode: str, expected: str) -> tuple[dict,dict]:
    need(root.is_dir() and not root.is_symlink() and
         {p.name for p in root.iterdir()}=={'capture','conversion','imported'},'OWNED_SLITHER_CASE_INVENTORY')
    capture = _manifest(root/'capture',CAPTURE_FILES)
    conversion_hashes = _manifest(root/'conversion',CONVERSION_FILES)
    need(read_artifact(root,'capture/source.sol')==SOURCES[mode],'OWNED_SLITHER_SOURCE_BYTES')
    execution = strict_json(read_artifact(root,'capture/execution.json'))
    wanted = {'schema_version':1,'mode':mode,'source_digest':expected,'returncode':0,
              'timed_out':False,'report_present':True,'admission_present':True}
    need(canonical(execution)==canonical(wanted),'OWNED_SLITHER_EXECUTION')
    need(read_artifact(root,'capture/admission.json')==canonical(_admission(mode,expected)),
         'OWNED_SLITHER_ADMISSION')
    normalized,converted = convert_original(read_artifact(root,'capture/slither-original.json'),mode)
    need(read_artifact(root,'conversion/slither-normalized.json')==normalized and
         read_artifact(root,'conversion/conversion.json')==canonical(converted) and
         read_artifact(root,'conversion/context.json')==canonical(context(mode,sha(normalized))),
         'OWNED_SLITHER_CONVERSION_BINDING')
    result = static_review.verify_report(root/'imported')
    files = static_review.BASE_FILES | {static_review._source_artifact(sha(SOURCES[mode]))}
    imported = _manifest(root/'imported',files)
    need(read_artifact(root,'imported/slither.json')==normalized and
         read_artifact(root,'imported/context.json')==canonical(context(mode,sha(normalized))),
         'OWNED_SLITHER_IMPORT_BINDING')
    need(result['normalization_complete'] is True and result['unbound_alerts']==0 and
         result['source_sha256']=={'Owned.sol':sha(SOURCES[mode])} and
         all(alert['check']=='tx-origin' and alert['source_bound'] is True for alert in result['alerts']),
         'OWNED_SLITHER_UNBOUND_OBSERVATION')
    # Keep semantic locations/classification; private paths and audit timestamps
    # remain bound in the original bundle but are not cross-run identities.
    keys = ('fingerprint','check','tool_impact','tool_confidence','locations','occurrences')
    observation = {'mode':mode,'source_sha256':sha(SOURCES[mode]),'expected_rule_alert':mode=='positive',
                   'detected':result['unique_alert_count']>0,'raw_alert_count':result['raw_alert_count'],
                   'unique_alert_count':result['unique_alert_count'],
                   'alerts':[{key:alert[key] for key in keys} for alert in result['alerts']]}
    evidence = {'capture':capture,'conversion':conversion_hashes,'imported':imported}
    return observation,evidence


def _collect(root: Path, expected: str, complete: bool) -> dict:
    need(root.is_dir() and not root.is_symlink() and
         {p.name for p in root.iterdir()}==({'cases','review'} if complete else {'cases'}),
         'OWNED_SLITHER_STAGE_INVENTORY')
    cases = root/'cases'
    need(cases.is_dir() and not cases.is_symlink() and
         {p.name for p in cases.iterdir()}==set(SOURCES),'OWNED_SLITHER_CASE_COVERAGE')
    observations,evidence = [],{}
    for mode in sorted(SOURCES):
        observed,hashes = _observe(cases/mode,mode,expected)
        observations.append(observed);evidence[mode]=hashes
    counts = {key:0 for key in ('tp','tn','fp','fn')}
    for row in observations:
        key = ('tp' if row['detected'] else 'fn') if row['expected_rule_alert'] else ('fp' if row['detected'] else 'tn')
        counts[key] += 1
    return {'schema_version':1,'profile':PROFILE,'status':'OWNED_SLITHER_NATIVE_EVALUATED',
        'source_digest':expected,'fixture_source_commit':FIXTURE_COMMIT,'observations':observations,
        'fixture_provenance':fixture_cases.fixture_provenance(),
        'evidence_sha256':evidence,'counts':counts,'case_unit':'one-fixed-owned-detector-control',
        'positive_denominator':1,'negative_denominator':2,
        'false_positive_rate':counts['fp']/2,'omission_rate':counts['fn']/1,
        'all_expected_control_results':counts['fp']==counts['fn']==0,
        'dependencies':dependencies.expected_identity(),'network':network.expected_proof(),
        'worker_policy':WORKER_POLICY,'solc_sha256':native_compile.PIN['sha256'],
        'original_reports_preserved':True,'generic_importer_weakened':False,
        'native_reexecution_required_for_verification':True,'shared_host_and_compiler':True,
        'comparison_control_is_not_security_proof':True,'producer_authenticated':False,
        'independent_producers_proved':False,'process_memory_integrity_proved':False,
        'host_filesystem_isolated':False,'blind_benchmark':False,'generalization_established':False,
        'external_targets_executed':0,'vulnerability_confirmed':False,'platform_complete':False,
        'global_progress':'not determined'}


def _documents(result: dict) -> dict:
    c = result['counts']
    review = (f"# Three fixed own Slither controls\n\nProfile: {PROFILE}.\n"
              f"Source: {result['source_digest']}.\nTP {c['tp']}; TN {c['tn']}; FP {c['fp']}; FN {c['fn']}.\n"
              "One positive and two detector-specific negative controls; the comparison control is not a contract-security proof.\n"
              "Original JSON and explicit conversion are both preserved. Generic external imports remain strict.\n"
              "Verification must rerun all three native cases with the pinned compiler, dependencies and socket filter.\n"
              "Same host/compiler; no producer authentication, complete host sandbox, blind benchmark or generalization proof.\n"
              "No external targets, original vulnerability, deployment or financial claim. Global progress not determined.\n")
    return {'evaluation.json':canonical(result),'REVIEW.md':review.encode()}


def create(out: Path, solc: Path, expected: str) -> dict:
    prior._allow_output(out);snapshot = source_identity(expected)
    dependencies.verify_dependencies();network.library_bytes();image=native_compile.read_pinned_binary(solc)
    out.parent.mkdir(parents=True,exist_ok=True);out.mkdir(mode=0o700);(out/'cases').mkdir(mode=0o700)
    for mode in sorted(SOURCES): _run_case(mode,out/'cases'/mode,image,expected)
    result = _collect(out,expected,False)
    dependencies.verify_dependencies()
    need(snapshot==quality.source_snapshot() and result==_collect(out,expected,False),
         'OWNED_SLITHER_CHANGED_BEFORE_COMPLETION')
    write_new_bundle(out/'review',_documents(result))
    return result


def verify(root: Path, solc: Path, expected: str) -> dict:
    snapshot = source_identity(expected)
    marker = _manifest(root/'review',REVIEW_FILES);stored = _collect(root,expected,True)
    for name,raw in _documents(stored).items():
        need(read_artifact(root/'review',name)==raw,'OWNED_SLITHER_REVIEW_BINDING')
    with tempfile.TemporaryDirectory(prefix='owned-slither-replay-') as temp:
        replayed = create(Path(temp)/'fresh',solc,expected)
    semantic = lambda result:{key:value for key,value in result.items() if key!='evidence_sha256'}
    need(semantic(stored)==semantic(replayed),'OWNED_SLITHER_NATIVE_REPLAY_DIFFERS')
    need(snapshot==quality.source_snapshot() and marker==_manifest(root/'review',REVIEW_FILES) and
         stored==_collect(root,expected,True),'OWNED_SLITHER_CHANGED_DURING_REPLAY')
    return {'status':'OWNED_SLITHER_NATIVE_REPLAY_MATCH','source_digest':expected,
            'counts':stored['counts'],'all_expected_control_results':stored['all_expected_control_results'],
            'native_cases_reexecuted':3,'producer_authenticated':False,'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Evaluate/replay three fixed own Slither controls')
    subs = parser.add_subparsers(dest='command',required=True)
    build = subs.add_parser('evaluate-owned-slither-native');build.add_argument('--out',type=Path,required=True)
    check = subs.add_parser('verify-owned-slither-native');check.add_argument('--bundle',type=Path,required=True)
    for sub in (build,check):
        sub.add_argument('--solc',type=Path,required=True);sub.add_argument('--expected-source',required=True)
    args = parser.parse_args(argv)
    try:
        result = (create(args.out,args.solc,args.expected_source) if args.command=='evaluate-owned-slither-native'
                  else verify(args.bundle,args.solc,args.expected_source))
        print(json.dumps({key:result[key] for key in ('status','source_digest','counts','all_expected_control_results','vulnerability_confirmed')},sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError,RecursionError,subprocess.TimeoutExpired):
        print(json.dumps({'status':'OWNED_SLITHER_NATIVE_BLOCKED','vulnerability_confirmed':False}));return 2


if __name__=='__main__':
    raise SystemExit(main())
