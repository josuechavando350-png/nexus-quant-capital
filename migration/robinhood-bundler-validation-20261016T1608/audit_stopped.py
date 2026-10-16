"""Offline audit of the actual stopped four-request pilot, not a new capture."""
import hashlib
import json
from pathlib import Path
from validation import HERE, PM, CASES, fixture, read, keccak256, summarize
from run_local import verify_lock


def need(ok, message):
    if not ok:
        raise ValueError(message)


def failed_op(raw):
    data = bytes.fromhex(raw.removeprefix('0x'))
    need(data[:4] == keccak256(b'FailedOpWithRevert(uint256,string,bytes)')[:4], 'wrong outer error')
    data = data[4:]
    def number(offset):
        need(offset >= 0 and offset % 32 == 0 and offset+32 <= len(data), 'invalid ABI offset')
        return int.from_bytes(data[offset:offset+32], 'big')
    need(number(32) == 96, 'wrong reason offset')
    reason_size = number(96)
    reason_end = 128 + ((reason_size+31)//32)*32
    need(number(64) == reason_end, 'wrong inner offset')
    inner_size = number(reason_end)
    need(len(data) == reason_end+32+((inner_size+31)//32)*32, 'wrong error length')
    reason = data[128:128+reason_size].decode('utf8')
    inner = data[reason_end+32:reason_end+32+inner_size]
    need(not any(data[128+reason_size:reason_end]), 'nonzero reason padding')
    need(not any(data[reason_end+32+inner_size:]), 'nonzero inner padding')
    return {'op_index': number(0), 'reason': reason, 'inner': '0x'+inner.hex()}


def audit(out):
    verify_lock()
    report, rows = read(out/'report.json'), read(out/'requests.json')
    need(report['status'] == 'STOPPED_PREFIX_PRESERVED', 'not preserved stop')
    need(report['registration_commit'] == 'dae502a2d0f26ce16a7a9d286ff889fb26d5af42', 'registration changed')
    need(report['cases'] == [] and report['local_rpc_methods'] == 4, 'invented successful cases')
    need(report['public_rpc_methods'] == report['transactions_sent'] == 0, 'scope changed')
    need(report['full_bundler_executed'] is False, 'bundler overclaim')
    need([r['request']['method'] for r in rows] == ['web3_clientVersion', 'eth_chainId', 'eth_getBlockByNumber', 'debug_traceCall'], 'request order/prefix')
    responses = []
    for i, row in enumerate(rows, 1):
        need(row['request']['id'] == i and row['http_status'] == 200 and 'error' not in row, 'RPC envelope/HTTP')
        body = (out/row['file']).read_bytes()
        need(hashlib.sha256(body).hexdigest() == row['response_sha256'], 'response hash changed')
        response = json.loads(body)
        need(response['id'] == i and 'error' not in response, 'RPC error')
        responses.append(response['result'])
    gaps = [(b['dispatch_seconds']-a['dispatch_seconds'])*1000 for a,b in zip(rows,rows[1:])]
    need(min(gaps) >= 350 and report['elapsed_seconds'] < 900, 'global limits')
    need(int(responses[1],16) == 4663 and int(responses[2]['number'],16) == 0, 'local chain')
    case = fixture(CASES[0])
    need(read(out/(CASES[0]+'-input.json')) == case, 'fixture changed')
    tx, block_hash, options = rows[-1]['request']['params']
    need(tx == case['transaction'] and block_hash == responses[2]['hash'], 'input/hash differs')
    need(options == {'tracer': (HERE/'build/tracer.js').read_text(), 'timeout':'10s', 'reexec':0, 'stateOverrides':case['stateOverrides']}, 'trace options differ')
    trace = responses[-1]
    need(trace['calls'][-1]['type'] == 'REVERT', 'terminal not reverted')
    decoded = failed_op(trace['calls'][-1]['data'])
    need(decoded == {'op_index':0, 'reason':'AA23 reverted', 'inner':'0x'+keccak256(b'ECDSAInvalidSignature()')[:4].hex()}, 'unexpected validation failure')
    precompile = '0x'+'0'*39+'1'
    pos = next(i for i,c in enumerate(trace['calls']) if c.get('to') == precompile)
    need(trace['calls'][pos+1] == {'type':'RETURN','gasUsed':0,'data':'0x'}, 'precompile return differs')
    need(not any(x['topLevelTargetAddress'].lower() == PM for x in trace['callsFromEntryPoint']), 'paymaster unexpectedly reached')
    need(precompile in case['stateOverrides'], 'missing colliding override')
    need(trace['keccak'][0].endswith(case['window']['approved_userop_hash'][2:]), 'userop hash mismatch')
    try:
        summarize(case, trace)
    except ValueError as error:
        need(report['error'] == type(error).__name__+': '+str(error), 'stop replay mismatch')
    else:
        raise ValueError('unexpected successful replay')
    source = (HERE/'evidence/diagnosis/geth-override.go').read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest()
    need(blob == 'd3644570325c499d40af7006d4e409ab8067476b', 'upstream source blob differs')
    return {'audit':'EXACT_STOP_RECONSTRUCTED', 'decoded_error':decoded,
            'rpc_methods_local':4,'rpc_methods_public':0,'transactions':0,
            'minimum_dispatch_gap_ms':min(gaps), 'wait_seconds':sum(r['wait_seconds'] for r in rows),
            'process_seconds':report['elapsed_seconds'], 'successful_validation_cases':0,
            'validation_attempts':1,'planned_cases':5,'paymaster_reached':False,
            'final_header_check_performed':False,'full_bundler_admission_proven':False,
            'precompile_1_override':case['stateOverrides'][precompile],
            'userop_hash_matches_fixture':True, 'upstream_override_git_blob':blob,
            'diagnosis':'Geth removes an overridden active precompile even for passive balance/storage fields. Trace matches empty native-signature call. Source-supported adapter defect; corrected capture still required.',
            'funding_available_proven':False,'profit_proven':False}


if __name__ == '__main__':
    print(json.dumps(audit(HERE/'evidence/pilot'), indent=2))
