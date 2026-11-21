"""Measure exact-name lookups through the real resident CLI, including pipe IO and JSON decoding."""
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns

from superhunter.privacy import PrivateArgumentParser


def main():
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    args = parser.parse_args()
    # Both producer links, an inventory-only entry, Python and Cargo pins, and a miss.
    keys = ('anchore/syft', 'cvc5/cvc5', 'crytic/slither', 'cryptography', 'sha2', 'absent.example/project')
    argv = [sys.executable, '-m', 'superhunter', 'query-product', '--bundle', str(args.bundle)]
    start = perf_counter_ns()
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as worker:
        def ask(key):
            worker.stdin.write(key + '\n')
            worker.stdin.flush()
            return json.loads(worker.stdout.readline())

        if ask(keys[0]).get('catalog_id') != 136:
            raise ValueError('first query returned wrong project')
        startup = perf_counter_ns() - start
        samples = []
        for n in range(6000):
            key = keys[n % len(keys)]
            start = perf_counter_ns()
            row = ask(key)
            samples.append(perf_counter_ns() - start)
            if '/' in key:
                valid = row is None if key == keys[-1] else isinstance(row, dict) and row.get('repository') == key
            else:
                valid = bool(row) and all(pin['name'] == key for pin in row['pins']) and bool(row['pins'])
            if not valid:
                raise ValueError('query returned wrong evidence')
        worker.stdin.close()
        if worker.wait(timeout=10):
            raise RuntimeError('query worker failed')
    samples.sort()
    print(json.dumps({'method': 'resident CLI request/response including decoding',
                      'lookups': len(samples), 'first_response_ms': startup / 1e6,
                      'latency_ms': {f'p{p}': samples[math.ceil(len(samples) * p / 100)-1] / 1e6
                                     for p in (50, 95, 99)}}))


if __name__ == '__main__':
    main()
