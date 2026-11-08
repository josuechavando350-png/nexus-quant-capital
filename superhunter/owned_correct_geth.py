"""Execute only the correct own source on sixteen fixed counter-controls in Geth."""
from copy import deepcopy
from pathlib import Path
import re

from . import owned_correct_evm_cases as cases, owned_quota_execution as transport
from . import quality
from .safe_io import canonical

need, sha, evm, compiler = cases.need, cases.sha, cases.evm, cases.compiler


def execute_fixed(solc: Path, geth: Path, digest: str, sealed_fd: int) -> dict:
    need(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest), 'CORRECT_EVM_SOURCE_REFERENCE')
    before = quality.source_snapshot()
    need(sha(canonical(before)) == digest, 'CORRECT_EVM_SOURCE_CHANGED')
    solc_image, geth_image = compiler.read_pinned_binary(solc), evm.read_evm(geth)
    compiled = {(v, c): cases.compile_owned(solc_image, v, c)
                for v in cases.VARIANTS for c in cases.CODEGEN}
    constructors, rows = [], []
    for case, codegen in cases.inventory():
        built = compiled[case['variant'], codegen]
        contract = built['contract']
        birth = transport.run(geth_image, prestate=evm.genesis(), sealed_fd=sealed_fd,
            creation=contract['evm']['bytecode']['object'])['observed']
        need(birth['error'] is None and birth['return_data'] ==
             '0x' + contract['evm']['deployedBytecode']['object'] and
             cases.decode(birth['alloc'], contract) == cases.INITIAL, 'CORRECT_EVM_CONSTRUCTOR')
        constructors.append({'case_id': case['case_id'], 'codegen': codegen,
                             'initial_state': deepcopy(cases.INITIAL),
                             'runtime_sha256': built['record']['runtime_sha256']})
        alloc = birth['alloc']
        for call_index, item in enumerate(cases.schedule(case['events'])):
            previous = cases.decode(alloc, contract)
            result = transport.run(geth_image, prestate=evm.genesis(alloc, gas=item['gas']),
                gas=item['gas'], sealed_fd=sealed_fd,
                calldata=contract['evm']['methodIdentifiers']['step(uint256)'] + format(item['word'], '064x'))
            actual = result['observed']
            need(actual['error'] in (None, 'execution reverted', 'out of gas'), 'CORRECT_EVM_ERROR')
            status = {None: 'COMMITTED', 'execution reverted': 'REVERTED', 'out of gas': 'OUT_OF_GAS'}[actual['error']]
            if status != 'COMMITTED':
                need(canonical(actual['alloc']) == canonical(alloc), 'CORRECT_EVM_FAILED_PERSISTENCE')
            rows.append({'case_id': case['case_id'], 'codegen': codegen, 'call_index': call_index,
                'event_index': item['event_index'], 'probe': item['probe'],
                'observation': {'before': previous, 'after': cases.decode(actual['alloc'], contract),
                    'word': item['word'], 'gas': item['gas'], 'status': status,
                    'return_data': actual['return_data']},
                'state_root': actual['state_root'], 'stdout_sha256': sha(result['stdout_utf8'].encode())})
            alloc = actual['alloc']
    need(quality.source_snapshot() == before, 'CORRECT_EVM_SOURCE_CHANGED_DURING_RUN')
    return {'schema_version': 1, 'profile': cases.PROFILE, 'source_digest': digest,
        'engine': 'geth', 'fork': 'Cancun', 'solc_sha256': sha(solc_image),
        'geth_sha256': sha(geth_image), 'builds': [b['record'] for b in compiled.values()],
        'constructors': constructors, 'rows': rows, 'compiler_runs': len(compiled),
        'constructor_executions': len(constructors), 'runtime_calls': len(rows)}
