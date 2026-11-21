"""Atheris over one fixed owned debit parser, inside a disconnected namespace."""
import importlib.util
import json
from pathlib import Path
import resource
import sys


def main():
    modes = {'buggy_campaign', 'buggy_replay', 'fixed_replay', 'fixed_campaign', 'clean_buggy'}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        raise ValueError('unknown owned Python fuzzing mode')
    mode = sys.argv[1]
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    def audit(event, args):
        if event.startswith('socket.'):
            raise PermissionError('owned Python fuzzing cannot open sockets')
    sys.addaudithook(audit)
    sys.path.insert(0, str(Path(__file__).resolve().parent/'lib'))
    import atheris
    from importlib.metadata import version
    spec = importlib.util.spec_from_file_location('owned_debit', Path('Owned.py'))
    owned = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owned)
    owned.debit = atheris.instrument_func(owned.debit)
    observed = []

    @atheris.instrument_func
    def check(data):
        if not observed:
            modules = {name: Path(sys.modules[name].__file__).name for name in
                       ('atheris.native', 'atheris.core_with_libfuzzer')}
            Path('engine.json').write_text(json.dumps({
                'version': version('atheris'), 'mode': mode, 'native_modules': modules}))
        result = owned.debit(data)
        observed.append({'input_hex': data.hex(), 'observed_remaining': result})
        Path('executed-inputs.json').write_text(json.dumps({'observations': observed}))
        if len(data) != 2:
            if result is not None:
                raise AssertionError('OWNED_INVALID_LENGTH_ACCEPTED')
            return
        balance, amount = data
        expected = balance - amount if amount <= balance else None
        if result != expected:
            Path('owned-violation.json').write_text(json.dumps({
                'input_hex': data.hex(), 'balance': balance, 'amount': amount,
                'observed_remaining': result, 'expected_remaining': expected,
                'property': 'rejected_overdraft_or_exact_debit'}))
            raise AssertionError('OWNED_ACCOUNTING_UNDERFLOW')

    replay = mode in ('buggy_replay', 'fixed_replay', 'clean_buggy')
    inputs = sorted(str(p) for p in Path('clean').glob('*.bin')) if mode == 'clean_buggy' else \
        ['case.bin'] if replay else ['corpus']
    arguments = ['owned-python-fuzzer', *inputs, '-seed=20261121',
                 '-max_len=3' if mode == 'clean_buggy' else '-max_len=2',
                 '-runs=1' if replay else '-runs=512', '-rss_limit_mb=512', '-timeout=3',
                 '-print_final_stats=1', '-exact_artifact_path=counterexample.bin']
    atheris.Setup(arguments, check, enable_python_coverage=True)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
