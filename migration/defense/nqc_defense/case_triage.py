"""Deterministic, evidence-linked prioritization of a selected set of authentication cases."""
from dataclasses import dataclass
from pathlib import Path

from .case_evidence import MAX_BUNDLE as MAX_EVIDENCE, verify_bundle as verify_evidence
from .case_review import CURRENT_SCHEMA, SCHEMA as LEGACY_REVIEW, initial_state, transition
from .codec import Rejected, canonical, decode, fields, identifier, integer
from .dossier_attestation import MAX_ATTESTATION, private_parent
from .files import publish_local, read_local, relative_parts, sha256
from .receipts import hex_digest
from .review_credentials import checkpoint as credential_checkpoint
from .review_dossier import MAX_DOSSIER, SCHEMA as DOSSIER_SCHEMA, row_budget, validate_pins
from .case_review import MAX_CASE_REVISIONS
from .signer_registry import ORIGIN, VerifiedRegistry, checkpoint

SCHEMA = 'nqc-auth-triage-policy-v1'
REPORT_SCHEMA = 'nqc-auth-triage-report-v1'
MAX_POLICY = 16384
MAX_ITEMS = 64
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_SELECTION = 256 * 1024
MAX_REPORT = 2 * 1024 * 1024
ITEM_FIELDS = ('registration_receipt','attestation','attestation_digest','dossier','dossier_digest','pins')


@dataclass(frozen=True, slots=True, init=False)
class TriagePolicy:
    """Externally pinned, immutable policy. Criticality is an operator-supplied assertion."""
    _data: bytes
    digest: str

    def __init__(self, data, digest):
        hex_digest(digest)
        value = decode(data,max_bytes=MAX_POLICY,max_nodes=256)
        if sha256(data) != digest: raise Rejected('triage_policy_digest')
        fields(value,('schema','policy_id','revision','tenant','asset','registry_digest','authority_digest',
                      'review_policy_digest','asset_criticality','weights','bands'))
        if value['schema'] != SCHEMA or canonical(value) != data: raise Rejected('triage_policy_schema')
        for key in ('policy_id','tenant','asset'): identifier(value[key])
        integer(value['revision'],1,2**63-1); integer(value['asset_criticality'],1,5)
        for key in ('registry_digest','authority_digest','review_policy_digest'): hex_digest(value[key])
        weights = value['weights']; fields(weights,('criticality','trigger_record','trigger_record_cap','needs_response','inconclusive'))
        integer(weights['criticality'],1,1000); integer(weights['trigger_record_cap'],1,100)
        for key in ('trigger_record','needs_response','inconclusive'): integer(weights[key],0,1000)
        bands = value['bands']; fields(bands,('normal','high','urgent'))
        integer(bands['normal'],1,1000000); integer(bands['high'],bands['normal']+1,1000000)
        integer(bands['urgent'],bands['high']+1,1000000)
        object.__setattr__(self,'_data',data); object.__setattr__(self,'digest',digest)

    @property
    def value(self):
        return decode(self._data,max_bytes=MAX_POLICY,max_nodes=256)


def prepare_items(items):
    """Bound and copy request metadata before any cryptographic work or database lock."""
    if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS: raise Rejected('triage_item_count')
    result = []; total = 0; identities = set()
    for item in items:
        fields(item,ITEM_FIELDS); validate_pins(item['pins'])
        pins = decode(canonical(item['pins']),max_bytes=4096)
        receipt = checkpoint(item['registration_receipt'])
        for key in ('attestation_digest','dossier_digest'): hex_digest(item[key])
        for key,maximum in (('attestation',MAX_ATTESTATION),('dossier',MAX_DOSSIER)):
            if type(item[key]) is not bytes or len(item[key]) > maximum: raise Rejected('triage_item_bytes')
            total += len(item[key])
        if total > MAX_INPUT_BYTES: raise Rejected('triage_input_budget')
        identity = (pins['tenant'],pins['asset'],pins['case_id'])
        if identity in identities: raise Rejected('triage_duplicate_case')
        identities.add(identity)
        result.append({**item,'pins':pins,'registration_receipt':dict(receipt)})
    return result


def _review_projection(value, pins, report):
    """Cross-check signed report fields against signed dossier rows, without claiming HMAC replay."""
    rows = value['review_rows']; row_budget(rows,MAX_CASE_REVISIONS)
    if not rows: raise Rejected('triage_review_required')
    state = initial_state(); previous = ORIGIN['head']; timeline = []
    last_time = -1
    for number,(revision,payload,parent,head) in enumerate(rows,1):
        if revision != number or parent != previous: raise Rejected('triage_review_sequence')
        event = decode(payload.encode(),max_bytes=16384)
        names = ('schema','policy_digest','tenant','asset','case_id','case_digest','config_digest','bundle_digest',
                 'actor','request_id','action','reason','verdict','recorded_ns')
        if type(event) is dict and event.get('schema') == CURRENT_SCHEMA: names += ('credential_checkpoint',)
        fields(event,names)
        if event['schema'] not in (LEGACY_REVIEW,CURRENT_SCHEMA): raise Rejected('triage_review_schema')
        if canonical(event).decode() != payload: raise Rejected('triage_review_encoding')
        for key in ('policy_digest','tenant','asset','case_id','case_digest','config_digest'):
            if event[key] != pins[key]: raise Rejected('triage_review_binding')
        if event['bundle_digest'] != pins['evidence_digest']: raise Rejected('triage_review_binding')
        for key in ('actor','request_id','action'): identifier(event[key])
        if event['verdict'] is not None and type(event['verdict']) is not str: raise Rejected('review_verdict')
        timestamp = integer(event['recorded_ns'],0,2**63-1)
        if timestamp < last_time: raise Rejected('triage_review_time_order')
        if 'credential_checkpoint' in event: credential_checkpoint(event['credential_checkpoint'])
        state = transition(state,event,revision)
        timeline.append({'revision':revision,'row_head':head,'actor':event['actor'],'action':event['action'],
            'reason':event['reason'],'verdict':event['verdict'],'recorded_ns':timestamp,
            'credential_checkpoint':event.get('credential_checkpoint'),
            'interpretation':'recorded reviewer action; not independently verified human identity'})
        previous = head; last_time = timestamp
    if {'revision':len(rows),'head':previous} != pins['case_checkpoint']: raise Rejected('triage_review_checkpoint')
    if value['captured_ns'] < last_time: raise Rejected('triage_capture_time')
    expected_review = {'stage':state['stage'],'notes_count':state['notes_count'],'closed_by':state['closed_by'],
                       'checkpoint':pins['case_checkpoint']}
    assessment = state['assessment']
    if assessment is not None:
        assessment = {**assessment,'row_head':rows[assessment['revision']-1][3],'classification':'analyst_claim'}
    if (canonical(expected_review) != canonical(report['facts']['review']) or
            canonical(assessment) != canonical(report['assessment']) or canonical(timeline) != canonical(report['timeline'])):
        raise Rejected('triage_report_review_discrepancy')
    return state


def _project(item, registered):
    pins = item['pins']; report = registered['signature_report']['signer_report']
    value = decode(item['dossier'],max_bytes=MAX_DOSSIER,max_nodes=131072)
    fields(value,('schema','captured_ns','policy','evidence','credential_rows','review_rows','clock_row'))
    if value['schema'] != DOSSIER_SCHEMA or canonical(value) != item['dossier']: raise Rejected('triage_dossier_schema')
    if sha256(canonical(value['policy'])) != pins['policy_digest']: raise Rejected('triage_review_policy_binding')
    integer(value['captured_ns'],0,2**63-1)
    if type(report['captured_ns']) is not int or value['captured_ns'] != report['captured_ns']:
        raise Rejected('triage_capture_binding')
    body = canonical(value['evidence'])
    if len(body) > MAX_EVIDENCE: raise Rejected('evidence_bundle_size')
    evidence = verify_evidence(body,pins['evidence_digest'],pins['tenant'],pins['asset'],pins['case_id'],
                               pins['case_digest'],pins['config_digest'])
    case = value['evidence']['case']
    expected_trigger = {'count':evidence['records'],'event_ids':case['evidence_event_ids'],
                        'evidence_digest':pins['evidence_digest'],'origin_authenticated':False}
    if (canonical(report['facts']['trigger_records']) != canonical(expected_trigger) or
            canonical(report['facts']['case_snapshot']) != canonical({'digest':pins['case_digest'],'detection_status':case['status']})):
        raise Rejected('triage_report_evidence_discrepancy')
    state = _review_projection(value,pins,report)
    return evidence['records'], state


def rank_dossiers(registry, policy, items):
    """All-or-nothing ranking at one pinned historical registry snapshot; no file/network/clock access."""
    if type(registry) is not VerifiedRegistry or type(policy) is not TriagePolicy: raise Rejected('triage_verified_inputs_required')
    selected = prepare_items(items); config = policy.value
    if (config['registry_digest'] != registry.registry_digest or config['authority_digest'] != registry.authority_digest):
        raise Rejected('triage_registry_scope')
    results = []; selection = []
    for item in selected:
        pins = item['pins']
        if any(pins[key] != config[key] for key in ('tenant','asset')) or pins['policy_digest'] != config['review_policy_digest']:
            raise Rejected('triage_case_scope')
        registered = registry.verify(item['registration_receipt'],item['attestation'],item['attestation_digest'],
                                     item['dossier'],item['dossier_digest'],pins)
        count,state = _project(item,registered); weights = config['weights']
        assessment = state['assessment']; verdict = assessment['verdict'] if assessment else None
        assessment_points = weights[verdict] if verdict in ('needs_response','inconclusive') else 0
        criticality_points = config['asset_criticality']*weights['criticality']
        trigger_points = min(count,weights['trigger_record_cap'])*weights['trigger_record']
        raw_score = criticality_points+trigger_points+assessment_points
        closed = state['stage'] == 'closed'; score = 0 if closed else raw_score
        urgency = 'closed' if closed else next((label for label in ('urgent','high','normal') if score >= config['bands'][label]),'low')
        contributions = [
            {'kind':'operator_asset_criticality','value':config['asset_criticality'],'weight':weights['criticality'],
             'points':criticality_points,'reference':{'digest':policy.digest,'pointer':'/asset_criticality'}},
            {'kind':'preserved_trigger_records','value':count,'cap':weights['trigger_record_cap'],'weight':weights['trigger_record'],
             'points':trigger_points,'reference':{'digest':pins['evidence_digest'],'pointer':'/records'}},
            {'kind':'analyst_claim','value':verdict,'points':assessment_points,
             'reference':{'digest':item['attestation_digest'],'pointer':'/statement/report/assessment'}},
            {'kind':'closed_case_adjustment','value':closed,'points':-raw_score if closed else 0,
             'reference':{'digest':item['attestation_digest'],'pointer':'/statement/report/facts/review'}}]
        refs = {'dossier_digest':item['dossier_digest'],'attestation_digest':item['attestation_digest'],
                'registration_receipt':dict(item['registration_receipt']),'pins':pins}
        results.append({'case_id':pins['case_id'],'score':score,'urgency':urgency,'review_stage':state['stage'],
                        'analyst_verdict':verdict,'trigger_records':count,'contributions':contributions,'references':refs})
        selection.append(refs)
    results.sort(key=lambda item:(item['review_stage']=='closed',-item['score'],item['case_id']))
    selection.sort(key=lambda item:item['pins']['case_id'])
    report = {'schema':REPORT_SCHEMA,'triage_policy_digest':policy.digest,'triage_policy':config,
              'registry_digest':registry.registry_digest,'registry_checkpoint':registry.checkpoint,
              'selected_proofs_digest':sha256(canonical(selection)),'selected_cases':len(results),'queue':results,
              'limits':{'selected_cases_only':True,'cross_asset_queue':False,'policy_weights_empirically_calibrated':False,
                        'score_is_compromise_probability':False,'automatic_response':False,'independent_freshness':False,
                        'origin_authenticated':False,'review_authorization_is_issuer_assertion':True,
                        'hmac_review_history_replayed_by_this_verifier':False,'independent_custody':False}}
    if len(canonical(report)) > MAX_REPORT: raise Rejected('triage_report_budget')
    return report


def load_selection(root, data, digest):
    """Read only explicitly selected files beneath an authorized private input root."""
    root = private_parent(root); hex_digest(digest)
    value = decode(data,max_bytes=MAX_SELECTION,max_nodes=8192)
    if sha256(data) != digest: raise Rejected('triage_selection_digest')
    fields(value,('schema','items'))
    if value['schema'] != 'nqc-auth-triage-selection-v1' or canonical(value) != data: raise Rejected('triage_selection_schema')
    entries = value['items']
    if type(entries) is not list or not 1 <= len(entries) <= MAX_ITEMS: raise Rejected('triage_item_count')
    prepared = []; total = 0
    for item in entries:
        fields(item,('registration_receipt','attestation_file','attestation_digest','dossier_file','dossier_digest','pins'))
        relative_parts(item['attestation_file']); relative_parts(item['dossier_file'])
        # Metadata is checked before opening files. Cumulative reads cannot exceed the batch budget.
        validate_pins(item['pins']); checkpoint(item['registration_receipt'])
        hex_digest(item['attestation_digest']); hex_digest(item['dossier_digest'])
        proof = {key:item[key] for key in ('registration_receipt','attestation_digest','dossier_digest','pins')}
        for name,maximum in (('attestation',MAX_ATTESTATION),('dossier',MAX_DOSSIER)):
            proof[name] = read_local(root,item[name+'_file'],min(maximum,MAX_INPUT_BYTES-total))
            total += len(proof[name])
        prepared.append(proof)
    return prepare_items(prepared)


def verify_output(data, digest, expected):
    """Compare bytes with a freshly recomputed mirror.triage result; no standalone trust claim."""
    hex_digest(digest)
    fields(expected,('schema','mirror_receipt','queue_report'))
    if type(data) is not bytes or len(data) > MAX_REPORT: raise Rejected('triage_report_budget')
    if sha256(data) != digest: raise Rejected('triage_report_digest')
    if data != canonical(expected): raise Rejected('triage_report_discrepancy')
    return {'verified':True,'report_digest':digest,'selected_cases':expected['queue_report']['selected_cases'],
            'mirror_receipt':expected['mirror_receipt'],'historical_snapshot_only':True}


def publish_output(output, report):
    output = Path(output).absolute(); private_parent(output.parent)
    data = canonical(report)
    if len(data) > MAX_REPORT: raise Rejected('triage_report_budget')
    publish_local(output.parent,output.name,data)
    persisted = read_local(output.parent,output.name,MAX_REPORT)
    verified = verify_output(persisted,sha256(data),report)
    return {'published':True,**verified,'bytes':len(data)}
