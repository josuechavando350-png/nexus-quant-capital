"""Run only the Solidity header parser from the digest-checked Wake wheel."""
import json
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path.cwd() / 'lib'))
    from wake.regex_parser.solidity_parser import SoliditySourceParser

    payload = json.load(sys.stdin)
    observations = {}
    for path, source in payload['sources'].items():
        versions, imports, digest, _ = SoliditySourceParser.parse_source(source.encode())
        observations[path] = {
            'imports': sorted(imports),
            'blake2b_256': digest.hex(),
            'accepts': {v: v in versions for v in payload['versions']},
        }
    print(json.dumps(observations))
