"""Evaluate fixed-width payload checks on generated, label-withheld representation cases."""
import argparse
from pathlib import Path
import random
import subprocess
import sys
import time

from superhunter.product_census_header import FIXTURE, FIXTURE_SHA, pinned
from superhunter.product_review import ROOT, sha
from superhunter.product_source_references import DENEB, DENEB_SHA, invalid_fields, payload_fields
from superhunter.safe_io import canonical, strict_json

# Hash of the fixed classifier, published before recording this evaluation.
CLASSIFIER = '4bad28ec8c01d71537cbf6f40ef48e433b42e5b22f06cadb00f123ddf288051a'
SEED = '9d7c9f8f34de7c46f69659781a3c622fc166a450c1bc649daad168e2e43df8ce'


def cases(seed, base):
    rng = random.Random(int(seed, 16))
    values = []
    for index in range(96):
        block = dict(base)
        block['gasUsed'] = hex(rng.getrandbits(64))
        block['miner'] = '0x' + rng.randbytes(20).hex()
        block['extraData'] = '0x' + rng.randbytes(rng.randrange(33)).hex()
        block['hash'] = '0x' + rng.randbytes(32).hex()
        error = []
        if index % 2:
            key, value = rng.choice([
                ('miner', '0x' + rng.randbytes(19).hex()),
                ('hash', '0x' + rng.randbytes(33).hex()),
                ('gasUsed', hex((1 << 64) + rng.getrandbits(32))),
                ('gasUsed', '0x0' + format(rng.randrange(1, 16), 'x')),
                ('extraData', '0x' + rng.randbytes(33).hex()),
                ('logsBloom', '0x' + rng.randbytes(255).hex())])
            block[key] = value
            error = [key]
        values.append((rng.randbytes(12).hex(), block, error))
    rng.shuffle(values)
    return ({k: block for k, block, _ in values}, {k: label for k, _, label in values})


def evaluate(checkout):
    pinned(ROOT, 'superhunter/product_source_references.py', CLASSIFIER)
    base = strict_json(pinned(ROOT, FIXTURE, FIXTURE_SHA))['block']
    inputs, labels = cases(SEED, base)
    start = time.monotonic()
    process = subprocess.run([sys.executable, '-B', '-m', 'superhunter.tools.evaluate_payload_types',
                              '--predict', str(checkout)], input=canonical(inputs), cwd=ROOT,
                             capture_output=True, timeout=30, check=True)
    elapsed = time.monotonic() - start
    output = strict_json(process.stdout)
    if set(output) != set(labels):
        raise ValueError('prediction coverage differs from case set')
    counts = {'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0}
    for key, truth in labels.items():
        predicted = bool(output[key])
        counts[{(True, True): 'tp', (False, False): 'tn', (True, False): 'fp',
                (False, True): 'fn'}[predicted, bool(truth)]] += 1
    return {**counts, 'cases': len(labels), 'exact_field_matches': sum(output[k] == v for k, v in labels.items()),
            'inputs_sha256': sha(canonical(inputs)), 'labels_sha256': sha(canonical(labels)),
            'predictions_sha256': sha(canonical(output)), 'prediction_wall_seconds': round(elapsed, 6),
            'classifier_sha256': CLASSIFIER, 'seed': SEED}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--predict', action='store_true')
    args = parser.parse_args()
    if args.predict:
        markdown = pinned(args.checkout/'upstream/189-consensus-specs', DENEB, DENEB_SHA).decode()
        fields = payload_fields(markdown)
        inputs = strict_json(sys.stdin.buffer.read(2_000_001))
        result = {key: invalid_fields(block, fields, 256, 32) for key, block in inputs.items()}
    else:
        result = evaluate(args.checkout.resolve())
    sys.stdout.buffer.write(canonical(result))


if __name__ == '__main__':
    main()
