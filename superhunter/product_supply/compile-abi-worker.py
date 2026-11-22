"""Child process for the four fixed product sources. Imports the reviewed local wheel set."""
import json
from pathlib import Path
import sys

root = Path.cwd()
sys.path.insert(0, str(root/'lib'))
from crytic_compile import CryticCompile
from crytic_compile.platform.solc_standard_json import SolcStandardJson

jobs = json.load(sys.stdin)
result = {}
for case, job in jobs.items():
    work = root/case
    work.mkdir()
    for path, source in job['sources'].items():
        (work/path).write_text(source['content'])
    compiler = CryticCompile(SolcStandardJson(job), solc=str(root/'solc'), solc_working_dir=str(work),
                             cwd=str(work), solc_disable_warnings=True)
    unit, = compiler.compilation_units.values()
    contracts = {}
    for source in unit.source_units.values():
        for name in source.contracts_names:
            contracts[name] = {sig: f'{selector:08x}' for sig, selector in source.hashes(name).items()}
    result[case] = contracts
print(json.dumps(result, sort_keys=True))
