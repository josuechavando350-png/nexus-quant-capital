"""Coherent local case dossiers and a path-free offline verifier; no independent custody claim."""
from pathlib import Path
import stat

from .case_evidence import MAX_BUNDLE, verify_bundle
from .case_review import MAX_CASE_REVISIONS, checkpoint as case_checkpoint, verify_case_rows
from .codec import Rejected, canonical, decode, fields, identifier, integer
from .files import publish_local, read_local, sha256
from .receipts import hex_digest
from .review_clock import MAX_TIME, ReviewClock
from .review_credentials import MAX_REVISIONS, checkpoint as credential_checkpoint, verify_credential_rows
from .review_policy import ReviewPolicyData

SCHEMA = 'nqc-review-dossier-v1'
MAX_DOSSIER = 32 * 1024 * 1024
MAX_HISTORY_BYTES = 16 * 1024 * 1024


def validate_pins(pins):
    fields(pins, ('tenant','asset','case_id','case_digest','config_digest','evidence_digest','policy_digest',
                  'case_checkpoint','credential_checkpoint','minimum_clock_ns'))
    identifier(pins['tenant']); identifier(pins['asset'])
    for key in ('case_id','case_digest','config_digest','evidence_digest','policy_digest'):
        hex_digest(pins[key])
    case_checkpoint(pins['case_checkpoint']); credential_checkpoint(pins['credential_checkpoint'])
    if pins['case_checkpoint']['revision'] == 0:
        raise Rejected('dossier_review_required')
    if pins['minimum_clock_ns'] is not None:
        integer(pins['minimum_clock_ns'],0,MAX_TIME)


def row_budget(rows, maximum):
    if type(rows) is not list or len(rows) > maximum:
        raise Rejected('dossier_row_count')
    size = 0
    for row in rows:
        if type(row) is not list or len(row) != 4:
            raise Rejected('dossier_row_shape')
        integer(row[0],1,maximum)
        if not isinstance(row[1],str):
            raise Rejected('dossier_row_payload')
        try:
            length = len(row[1].encode('utf-8'))
        except UnicodeError as exc:
            raise Rejected('dossier_row_payload') from exc
        if length > 16384:
            raise Rejected('dossier_row_payload')
        hex_digest(row[2]); hex_digest(row[3])
        size += length
        if size > MAX_HISTORY_BYTES:
            raise Rejected('dossier_history_budget')
    return size


def history_rows(history):
    return [[entry['revision'],canonical(entry['event']).decode(),entry['previous'],entry['head']] for entry in history]


def verify_dossier(data, digest, pins, audit_key):
    """Only supplied bytes and pins are used. No database, clock, file, or network reads."""
    validate_pins(pins); hex_digest(digest)
    if not isinstance(data,bytes) or len(data) > MAX_DOSSIER:
        raise Rejected('dossier_size')
    if sha256(data) != digest:
        raise Rejected('dossier_digest')
    value = decode(data,max_bytes=MAX_DOSSIER,max_nodes=131072)
    fields(value,('schema','captured_ns','policy','evidence','credential_rows','review_rows','clock_row'))
    if value['schema'] != SCHEMA or canonical(value) != data:
        raise Rejected('dossier_schema')
    captured = integer(value['captured_ns'],0,MAX_TIME)
    policy = ReviewPolicyData(canonical(value['policy']),pins['policy_digest'],audit_key)
    evidence_bytes = canonical(value['evidence'])
    if len(evidence_bytes) > MAX_BUNDLE:
        raise Rejected('evidence_bundle_size')
    evidence = verify_bundle(evidence_bytes,pins['evidence_digest'],pins['tenant'],pins['asset'],pins['case_id'],
                             pins['case_digest'],pins['config_digest'])
    size = row_budget(value['credential_rows'],MAX_REVISIONS) + row_budget(value['review_rows'],MAX_CASE_REVISIONS)
    if size > MAX_HISTORY_BYTES:
        raise Rejected('dossier_history_budget')
    credentials = verify_credential_rows(policy,value['credential_rows'])
    if credentials.current != pins['credential_checkpoint']:
        raise Rejected('dossier_credential_checkpoint')
    case = value['evidence']['case']
    _,state,current,history = verify_case_rows(policy,pins['tenant'],pins['asset'],pins['case_id'],
        (canonical(case),case['category'],case['status']),value['review_rows'],credentials)
    if current != pins['case_checkpoint']:
        raise Rejected('dossier_case_checkpoint')
    if not history or any(entry['event']['bundle_digest'] != pins['evidence_digest'] or
                          entry['event']['case_digest'] != pins['case_digest'] or
                          entry['event']['config_digest'] != pins['config_digest'] for entry in history):
        raise Rejected('dossier_evidence_binding')
    clock = ReviewClock(policy).verify_row(credentials,value['clock_row'])
    minimum = pins['minimum_clock_ns']
    if clock is None:
        if minimum is not None:
            raise Rejected('dossier_clock_unavailable')
    elif minimum is None or clock['observed_ns'] < minimum:
        raise Rejected('dossier_clock_minimum')
    times = [entry['event']['recorded_ns'] for entry in history + credentials.history]
    if clock is not None:
        if clock['credential_checkpoint'] != credentials.current or clock['observed_ns'] < max(times,default=0):
            raise Rejected('dossier_clock_snapshot')
        times.append(clock['observed_ns'])
    if captured < max(times,default=0):
        raise Rejected('dossier_capture_time')
    timeline = [{'revision':entry['revision'],'row_head':entry['head'],'actor':entry['event']['actor'],
                 'action':entry['event']['action'],'reason':entry['event']['reason'],'verdict':entry['event']['verdict'],
                 'recorded_ns':entry['event']['recorded_ns'],
                 'credential_checkpoint':entry['event'].get('credential_checkpoint'),
                 'interpretation':'recorded reviewer action; not independently verified human identity'} for entry in history]
    assessment = state['assessment']
    if assessment is not None:
        assessment = {**assessment,'row_head':history[assessment['revision']-1]['head'],'classification':'analyst_claim'}
    return {'verified':True,'schema':'nqc-review-dossier-report-v1','dossier_digest':digest,'captured_ns':captured,
            'tenant':pins['tenant'],'asset':pins['asset'],'case_id':pins['case_id'],
            'facts':{'trigger_records':{'count':evidence['records'],'event_ids':case['evidence_event_ids'],
                                       'evidence_digest':pins['evidence_digest'],'origin_authenticated':False},
                     'case_snapshot':{'digest':pins['case_digest'],'detection_status':case['status']},
                     'review':{'stage':state['stage'],'notes_count':state['notes_count'],'closed_by':state['closed_by'],
                               'checkpoint':current},
                     'credentials':{'changes':len(credentials.history),'checkpoint':credentials.current},
                     'clock':clock},
            'assessment':assessment,'timeline':timeline,
            'limits':{'verifies_recorded_snapshot_only':True,'current_authorization_checked':False,
                      'case_capture_time_independently_attested':False,'full_episode_history_included':False,
                      'independent_anchor':False,'legal_custody_claimed':False,'human_identity_verified':False,
                      'credential_hashes_and_policy_wide_history_included':True,'raw_review_key_fields_included':False,
                      'source_records_and_notes_require_private_handling':True}}


def capture_dossier(review, admin_key, pins, evidence_bytes, output):
    """Administrator-only export: the credential history covers the complete pinned policy."""
    review.credentials.administrator(admin_key)
    validate_pins(pins)
    if review.policy.digest != pins['policy_digest']:
        raise Rejected('dossier_policy_binding')
    verify_bundle(evidence_bytes,pins['evidence_digest'],pins['tenant'],pins['asset'],pins['case_id'],
                  pins['case_digest'],pins['config_digest'])
    with review.credentials.transaction() as db:
        review.credentials.administrator(admin_key)
        credentials = review.credentials.load(db)
        if credentials.current != pins['credential_checkpoint']:
            raise Rejected('dossier_credential_checkpoint')
        case,_,current,history = review._load(db,pins['tenant'],pins['asset'],pins['case_id'],credentials)
        if current != pins['case_checkpoint']:
            raise Rejected('dossier_case_checkpoint')
        if sha256(canonical(case)) != pins['case_digest']:
            raise Rejected('dossier_case_digest')
        captured = review.credentials.clock.observe(db,credentials)
        clock = db.execute('SELECT payload,mac FROM review_clock WHERE policy=?',(review.policy.digest,)).fetchone()
        value = {'schema':SCHEMA,'captured_ns':captured,'policy':review.policy.value,
                 'evidence':decode(evidence_bytes,max_bytes=MAX_BUNDLE,max_nodes=65536),
                 'credential_rows':history_rows(credentials.history),'review_rows':history_rows(history),
                 'clock_row':list(clock) if clock else None}
    data = canonical(value); digest = sha256(data)
    report = verify_dossier(data,digest,pins,admin_key)
    output = Path(output).absolute(); info = output.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise Rejected('dossier_output_directory_permissions')
    publish_local(output.parent,output.name,data)
    persisted = read_local(output.parent,output.name,MAX_DOSSIER)
    if persisted != data:
        raise Rejected('dossier_publication_changed')
    verify_dossier(persisted,digest,pins,admin_key)
    return {'published':True,'dossier_digest':digest,'bytes':len(data),'case_checkpoint':pins['case_checkpoint'],
            'credential_checkpoint':pins['credential_checkpoint'],'captured_ns':captured,
            'review_stage':report['facts']['review']['stage'],'snapshot_reverified':True,'independent_anchor':False}
