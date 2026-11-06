"""Compare explicit authentication policies using the same pinned corpus and real evaluator."""
from math import gcd
from pathlib import Path

from .auth_evaluation import evaluate, inputs
from .codec import Rejected, canonical
from .dossier_attestation import private_parent
from .files import publish_local, read_local, sha256
from .receipts import hex_digest

MAX_COMPARISON = 8 * 1024 * 1024


def _difference(before, after):
    """Exact candidate-minus-baseline ratio; undefined if either denominator is zero."""
    if not before['denominator'] or not after['denominator']:
        return None
    numerator = after['numerator']*before['denominator'] - before['numerator']*after['denominator']
    denominator = after['denominator']*before['denominator']
    divisor = gcd(abs(numerator),denominator)
    return {'numerator':numerator//divisor,'denominator':denominator//divisor}


def compare(corpus_data, corpus_digest, baseline_policy, baseline_digest, candidate_policy, candidate_digest):
    # Validate both choices before the first evaluation creates temporary stores.
    inputs(corpus_data,corpus_digest,baseline_policy,baseline_digest)
    inputs(corpus_data,corpus_digest,candidate_policy,candidate_digest)
    source_before = sha256(Path(__file__).read_bytes())
    before = evaluate(corpus_data,corpus_digest,baseline_policy,baseline_digest)
    after = evaluate(corpus_data,corpus_digest,candidate_policy,candidate_digest)
    if (before['implementation_sources'] != after['implementation_sources'] or
            source_before != sha256(Path(__file__).read_bytes())):
        raise Rejected('comparison_implementation_changed')
    old = {item['id']:item for item in before['scenarios']}
    new = {item['id']:item for item in after['scenarios']}
    if old.keys() != new.keys():
        raise Rejected('comparison_scenario_membership')
    scenarios = []; transitions = {}
    counters = {'alerts_introduced':0,'alerts_removed':0,'alerts_retained':0,'neither_alerted':0,
                'labeled_prediction_changes':0,'unlabeled_prediction_changes':0}
    for name in old:
        a,b = old[name],new[name]
        for field in ('format','label','input_digest','records','observations','rule_evaluated_records','excluded_by_kind','exclusion_reasons'):
            if a[field] != b[field]:
                raise Rejected('comparison_observation_discrepancy')
        state = ('alerts_retained' if a['case_opened'] else 'alerts_introduced') if b['case_opened'] else (
            'alerts_removed' if a['case_opened'] else 'neither_alerted')
        counters[state] += 1
        if a['case_opened'] != b['case_opened']:
            counters['unlabeled_prediction_changes' if a['label']=='unlabeled' else 'labeled_prediction_changes'] += 1
        transition = (a['classification'] or 'unlabeled')+'->'+(b['classification'] or 'unlabeled')
        transitions[transition] = transitions.get(transition,0)+1
        a_cases = {sha256(canonical(case)):case for case in a['cases']}
        b_cases = {sha256(canonical(case)):case for case in b['cases']}
        if len(a_cases) != len(a['cases']) or len(b_cases) != len(b['cases']):
            raise Rejected('comparison_duplicate_trigger_set')
        scenarios.append({'id':name,'label':a['label'],'input_digest':a['input_digest'],
            'prediction_change':state,'baseline_classification':a['classification'],
            'candidate_classification':b['classification'],'baseline_case_count':len(a_cases),
            'candidate_case_count':len(b_cases),'case_count_delta':len(b_cases)-len(a_cases),
            'retained_trigger_sets':sorted(a_cases.keys() & b_cases.keys()),
            'removed_trigger_sets':sorted(a_cases.keys()-b_cases.keys()),
            'introduced_trigger_sets':sorted(b_cases.keys()-a_cases.keys())})
    result = {'schema':'nqc-auth-policy-comparison-v1','corpus_digest':corpus_digest,
        'baseline_policy_digest':baseline_digest,'candidate_policy_digest':candidate_digest,
        'comparison_source_digest':source_before,'baseline_report_digest':sha256(canonical(before)),
        'candidate_report_digest':sha256(canonical(after)),'baseline_report':before,'candidate_report':after,
        'scenarios':scenarios,'prediction_changes':counters,'classification_transitions':transitions,
        'confusion_delta':{key:after['confusion_matrix'][key]-before['confusion_matrix'][key] for key in before['confusion_matrix']},
        'metric_delta':{key:_difference(before['metrics'][key],after['metrics'][key]) for key in before['metrics']},
        'delta_direction':'candidate_minus_baseline','same_episode_matching_claimed':False,
        'labels_are_operator_assertions':True,'independent_evaluation':False,
        'policy_recommendation':None,'production_policy_changed':False,'automatic_response':False}
    if len(canonical(result)) > MAX_COMPARISON:
        raise Rejected('comparison_report_budget')
    return result


def verify_comparison(data, digest, recomputed):
    """Caller must supply a fresh compare result from independently pinned inputs."""
    hex_digest(digest)
    if type(data) is not bytes or len(data) > MAX_COMPARISON:
        raise Rejected('comparison_report_budget')
    if sha256(data) != digest:
        raise Rejected('comparison_report_digest')
    if data != canonical(recomputed):
        raise Rejected('comparison_report_discrepancy')
    return {'verified':True,'comparison_digest':digest,'scenarios':len(recomputed['scenarios'])}


def publish_comparison(output, report):
    output = Path(output).absolute(); private_parent(output.parent)
    data = canonical(report)
    if len(data) > MAX_COMPARISON:
        raise Rejected('comparison_report_budget')
    publish_local(output.parent,output.name,data)
    return {'published':True,**verify_comparison(read_local(output.parent,output.name,MAX_COMPARISON),sha256(data),report)}
