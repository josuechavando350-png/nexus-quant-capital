"""Replay eight deterministic, label-withheld cohorts on the immutable NQC representation classifier."""
import argparse
from pathlib import Path
import sys

from superhunter.product_review import sha
from superhunter.safe_io import canonical
from superhunter.tools.evaluate_payload_types import CLASSIFIER, evaluate

PUBLISHED_PARENT = 'fe15278f965a0530d679376a68802dae0eee64b5'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--timing', type=Path, help='optional new file for actual wall times, excluded from immutable results')
    args = parser.parse_args()
    results, times = [], []
    for index in range(8):
        seed = sha(f'NQC PR115 header cohort {PUBLISHED_PARENT} {index}'.encode())
        run = evaluate(args.checkout.resolve(), seed)
        times.append(run.pop('prediction_wall_seconds'))
        results.append(run)
    totals = {key: sum(r[key] for r in results) for key in ('cases', 'tp', 'tn', 'fp', 'fn', 'exact_field_matches')}
    if args.timing:
        with args.timing.open('xb') as output:
            output.write(canonical({'per_cohort_seconds': times, 'total_prediction_seconds': round(sum(times), 6)}))
    sys.stdout.buffer.write(canonical({'classifier_sha256': CLASSIFIER, 'seed_source_commit': PUBLISHED_PARENT,
                                       'cohorts': results, 'totals': totals}))


if __name__ == '__main__':
    main()
