"""EVMole worker for fixed local runtime bytecode; launched without a network."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()/'evmole'))
from evmole import contract_info

payload = json.load(sys.stdin)
result = {}
for name, code in payload.items():
    info = contract_info(code, selectors=True, arguments=True, state_mutability=True)
    result[name] = [{'selector': f.selector, 'offset': f.bytecode_offset,
                     'dispatch': f.dispatch, 'arguments': f.arguments,
                     'state_mutability': f.state_mutability} for f in info.functions]
print(json.dumps(result, sort_keys=True))
