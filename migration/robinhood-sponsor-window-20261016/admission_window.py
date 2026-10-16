#!/usr/bin/env python3
"""Offline comparison of a bounded NQC window and pinned Rundler predicates.

No provider client, credentials, broadcast, or claim of full ERC-7562 admission.
The buffer is remaining validity, not a mandatory wait.
"""
BUFFER_SECONDS = 20
MAX_UINT48 = (1 << 48) - 1


def compare(valid_after, valid_until, now):
    for value in (valid_after, valid_until, now):
        if type(value) is not int or not 0 <= value <= MAX_UINT48:
            raise ValueError('timestamps must be unsigned uint48 integers')
    # NQC research policy deliberately rejects the v0.7 zero/infinite sentinel.
    if not 0 < valid_after < valid_until or valid_until - valid_after > 60:
        raise ValueError('a finite positive window of at most 60 seconds is required')
    return {
        'entrypoint_v07_time_check': valid_after <= now <= valid_until,
        'rundler_reference_simulation_time_check': valid_after <= now and now + BUFFER_SECONDS < valid_until,
        'rundler_reference_builder_time_check': valid_after <= now and now + BUFFER_SECONDS <= valid_until,
        'remaining_seconds': valid_until - now,
        'full_bundler_admission_proven': False,
    }
