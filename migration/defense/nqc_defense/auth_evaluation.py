"""Replay a pinned, bounded labeled corpus through real local ingestion and evidence capture."""
import base64
import binascii
from pathlib import Path
import tempfile

from .auth_log import AuthLogMonitor, MAX_LINE
from .case_evidence import capture_case, verify_bundle
from .codec import Rejected, canonical, decode, fields, identifier, integer
from .files import publish_local, read_local, sha256
from .operations import OperationsStore
from .openssh_log import source_options
from .receipts import hex_digest

MAX_CORPUS = 2 * 1024 * 1024
MAX_POLICY = 4096
MAX_REPORT = 2 * 1024 * 1024
MAX_SCENARIOS = 64
MAX_RECORDS = 4096
MAX_SCENARIO_RECORDS = 256
IMPLEMENTATION_FILES = ('auth_evaluation.py', 'auth_log.py', 'case_evidence.py',
                        'operations.py', 'openssh_log.py', 'codec.py', 'files.py', 'receipts.py')


def _document(data, digest, maximum):
    hex_digest(digest)
    if type(data) is not bytes or len(data) > maximum:
        raise Rejected('evaluation_input_budget')
    if sha256(data) != digest:
        raise Rejected('evaluation_input_digest')
    value = decode(data, max_bytes=maximum, max_nodes=16384)
    if canonical(value) != data:
        raise Rejected('evaluation_input_not_canonical')
    return value


def inputs(corpus_data, corpus_digest, policy_data, policy_digest):
    """Validate every scenario before creating a store or evaluating any record."""
    policy = _document(policy_data, policy_digest, MAX_POLICY)
    fields(policy, ('schema', 'threshold', 'window_seconds'))
    if policy['schema'] != 'nqc-auth-evaluation-policy-v1':
        raise Rejected('evaluation_policy_schema')
    integer(policy['threshold'], 2, 100)
    integer(policy['window_seconds'], 1, 86400)
    corpus = _document(corpus_data, corpus_digest, MAX_CORPUS)
    fields(corpus, ('schema', 'corpus_id', 'revision', 'origin', 'scenarios'))
    if corpus['schema'] != 'nqc-auth-evaluation-corpus-v1' or corpus['origin'] not in ('authored', 'user_supplied'):
        raise Rejected('evaluation_corpus_schema')
    identifier(corpus['corpus_id']); integer(corpus['revision'], 1, 2**31-1)
    scenarios = corpus['scenarios']
    if type(scenarios) is not list or not 1 <= len(scenarios) <= MAX_SCENARIOS:
        raise Rejected('evaluation_scenario_count')
    prepared, seen, total = [], set(), 0
    for scenario in scenarios:
        fields(scenario, ('id', 'format', 'expected_host', 'label', 'context', 'records_base64'))
        name = identifier(scenario['id'])
        if name in seen:
            raise Rejected('evaluation_duplicate_scenario')
        seen.add(name)
        source_options(scenario['format'], scenario['expected_host'])
        if scenario['label'] not in ('review', 'routine', 'unlabeled'):
            raise Rejected('evaluation_label')
        context = scenario['context']
        if not isinstance(context, str) or not 1 <= len(context) <= 1024:
            raise Rejected('evaluation_context')
        try:
            context.encode('utf-8')
        except UnicodeError as exc:
            raise Rejected('evaluation_context_encoding') from exc
        encoded = scenario['records_base64']
        if type(encoded) is not list or not 1 <= len(encoded) <= MAX_SCENARIO_RECORDS:
            raise Rejected('evaluation_record_count')
        total += len(encoded)
        if total > MAX_RECORDS:
            raise Rejected('evaluation_total_records')
        lines = []
        for value in encoded:
            if not isinstance(value, str) or len(value) > 4*((MAX_LINE+2)//3):
                raise Rejected('evaluation_record_size')
            try:
                raw = base64.b64decode(value, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise Rejected('evaluation_record_encoding') from exc
            if base64.b64encode(raw).decode('ascii') != value:
                raise Rejected('evaluation_record_encoding')
            if not 1 <= len(raw) <= MAX_LINE or not raw.endswith(b'\n') or b'\n' in raw[:-1]:
                raise Rejected('evaluation_record_framing')
            lines.append(raw)
        prepared.append((scenario, tuple(lines)))
    return corpus, policy, prepared


def _ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'parts_per_million': numerator * 1000000 // denominator if denominator else None}


def _metrics(matrix):
    tp, fp, tn, fn = (matrix[k] for k in ('true_positive','false_positive','true_negative','false_negative'))
    return {'precision': _ratio(tp,tp+fp), 'recall': _ratio(tp,tp+fn),
            'false_positive_rate': _ratio(fp,fp+tn), 'accuracy': _ratio(tp+tn,tp+tn+fp+fn)}


def evaluate(corpus_data, corpus_digest, policy_data, policy_digest, *, batch_size=17):
    """No network or caller paths: create temporary owned logs/stores, then reverify captured evidence."""
    integer(batch_size,1,1000)
    corpus, policy, scenarios = inputs(corpus_data,corpus_digest,policy_data,policy_digest)
    sources = {name:sha256((Path(__file__).parent/name).read_bytes()) for name in IMPLEMENTATION_FILES}
    matrix = {key:0 for key in ('true_positive','false_positive','true_negative','false_negative')}
    outputs, pending = [], []
    with tempfile.TemporaryDirectory(prefix='nqc-auth-evaluation-') as temporary:
        root = Path(temporary)
        for index, (scenario, lines) in enumerate(scenarios):
            log = root/f'input-{index}.log'; data = b''.join(lines); log.write_bytes(data)
            store = OperationsStore.create(root/f'state-{index}')
            monitor = AuthLogMonitor.register(store,'evaluation','evaluation','fixture',root,log.name,
                policy['threshold'],policy['window_seconds'],format_name=scenario['format'],
                expected_host=scenario['expected_host'])
            committed = 0
            for _ in range(len(lines)+1):
                result = monitor.poll(max_records=batch_size); committed += result['records_committed']
                monitor = AuthLogMonitor(OperationsStore(store.root),'evaluation',monitor.digest)
                if result['at_observed_eof']:
                    break
                if result['records_committed'] == 0:
                    raise Rejected('evaluation_ingestion_stalled')
            if committed != len(lines) or not result['at_observed_eof'] or monitor.poll()['records_committed'] != 0:
                raise Rejected('evaluation_ingestion_incomplete')
            events, cursor = [], 0
            while True:
                page = store.events('evaluation','fixture',after=cursor,limit=200)
                if not page: break
                events.extend(page); cursor = page[-1]['sequence']
            if len(events) != len(lines):
                raise Rejected('evaluation_event_count')
            offsets, offset = {}, 0
            for line_index, raw in enumerate(lines):
                offsets[offset] = (line_index,len(raw),sha256(raw)); offset += len(raw)
            observations = evaluated = 0; excluded = {}; reasons = {}
            for row in events:
                event = row['event']; evidence = event['evidence']; expected = offsets.get(evidence['start'])
                if expected is None or (evidence['end']-evidence['start'],evidence['raw_sha256']) != expected[1:]:
                    raise Rejected('evaluation_event_reference')
                observations += int(event['kind']=='auth.observation')
                evaluated += int(event['attributes']['rule_evaluated'])
                if not event['attributes']['rule_evaluated']:
                    excluded[event['kind']] = excluded.get(event['kind'],0)+1
                    reason = event['attributes'].get('rule_exclusion') or event['attributes'].get('reason') or event['kind']
                    reasons[reason] = reasons.get(reason,0)+1
            cases = store.cases('evaluation','fixture',limit=200)
            if len(cases) > len(lines)//policy['threshold']:
                raise Rejected('evaluation_case_count')
            case_refs = []
            for number, case in enumerate(cases):
                case_digest = sha256(canonical(case)); output = root/f'evidence-{index}-{number}.json'
                captured = capture_case(store,'evaluation','fixture',case['case_id'],case_digest,monitor.digest,
                    [{'generation':0,'name':log.name}],output)
                bundle = output.read_bytes()
                pending.append((bundle,captured['bundle_digest'],'evaluation','fixture',case['case_id'],case_digest,monitor.digest))
                value = decode(bundle,max_bytes=8*1024*1024,max_nodes=65536)
                refs = []
                for item in value['records']:
                    evidence = item['event']['evidence']; ref = offsets[evidence['start']]
                    refs.append({'record_index':ref[0],'raw_sha256':ref[2],
                                 'start':evidence['start'],'end':evidence['end']})
                case_refs.append({'trigger_records':refs,'trigger_conditions_verified':captured['trigger_conditions_verified']})
            case_refs.sort(key=lambda item: canonical(item))
            predicted = bool(cases); label = scenario['label']; bucket = None
            if label != 'unlabeled':
                positive = label == 'review'
                bucket = ('true_' if predicted == positive else 'false_')+('positive' if predicted else 'negative')
                matrix[bucket] += 1
            outputs.append({'id':scenario['id'],'format':scenario['format'],'label':label,
                'input_digest':sha256(data),'records':len(lines),'observations':observations,
                'rule_evaluated_records':evaluated,'excluded_by_kind':excluded,'exclusion_reasons':reasons,
                'case_opened':predicted,'cases':case_refs,'classification':bucket})
    # Prove the public evidence verifier does not depend on the temporary log/store.
    for args in pending:
        if not verify_bundle(*args)['trigger_conditions_verified']:
            raise Rejected('evaluation_evidence_not_verified')
    if sources != {name:sha256((Path(__file__).parent/name).read_bytes()) for name in IMPLEMENTATION_FILES}:
        raise Rejected('evaluation_source_changed')
    report = {'schema':'nqc-auth-evaluation-report-v1','corpus_digest':corpus_digest,
        'policy_digest':policy_digest,'corpus_id':corpus['corpus_id'],'corpus_revision':corpus['revision'],
        'declared_origin':corpus['origin'],'rule':'auth_failure_burst_v1','policy':policy,
        'implementation_sources':sources,'scenarios':outputs,'confusion_matrix':matrix,'metrics':_metrics(matrix),
        'labeled_scenarios':sum(matrix.values()),'unlabeled_scenarios':sum(s['label']=='unlabeled' for s in outputs),
        'evidence_bundles_verified_after_cleanup':len(pending),'reopened_without_duplicate_records':True,
        'labels_are_operator_assertions':True,'independent_evaluation':False,'origin_authenticated':False,
        'production_accuracy_claimed':False,'automatic_response':False}
    if len(canonical(report)) > MAX_REPORT:
        raise Rejected('evaluation_report_budget')
    return report


def verify_report(data, digest, recomputed):
    hex_digest(digest)
    if type(data) is not bytes or len(data) > MAX_REPORT:
        raise Rejected('evaluation_report_budget')
    if sha256(data) != digest:
        raise Rejected('evaluation_report_digest')
    if data != canonical(recomputed):
        raise Rejected('evaluation_report_discrepancy')
    return {'verified':True,'report_digest':digest,'labeled_scenarios':recomputed['labeled_scenarios']}


def publish_report(output, report):
    from .dossier_attestation import private_parent
    output = Path(output).absolute(); private_parent(output.parent)
    data = canonical(report)
    if len(data) > MAX_REPORT:
        raise Rejected('evaluation_report_budget')
    publish_local(output.parent,output.name,data)
    return {'published':True,**verify_report(read_local(output.parent,output.name,MAX_REPORT),sha256(data),report)}
