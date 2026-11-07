"""Bounded history-query reference, separate from the incremental detector.

Shares the abstract policy specification and input schema, not producer state or
truth labels. Agreement is not independent production or a completeness proof.
"""
from .owned_authority_model import validate_events


def expected_decisions(events: list) -> list[bool]:
    validate_events(events)
    decisions = []
    for index, event in enumerate(events):
        if event['op'] != 'use':
            decisions.append(True)
            continue
        history = [previous for previous in events[:index]
                   if previous['op'] in ('grant', 'revoke') and all(
                       previous[field] == event[field] for field in ('principal', 'tenant', 'action'))]
        credential = event['credential']
        decisions.append(bool(history and history[-1]['op'] == 'grant' and
            all(credential[field] == event[field] for field in ('principal', 'tenant', 'action')) and
            credential['generation'] == len(history)))
    return decisions
