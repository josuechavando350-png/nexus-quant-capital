"""Check conservation of balances on the owned T36 fixture with Wake and Forge."""
import ast
import hashlib
import json
import shutil
from random import Random
from typing import Optional

from .product_sources import git

SEED = 36020
CASES = 18


def funding_cases(folder, commit):
    # Load the unchanged standalone Wake generator without starting a chain or a debugger.
    code = git(folder, 'show', commit + ':wake/testing/fuzzing/generators.py')
    node = next(n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef) and n.name == 'random_int')
    namespace = {'Optional': Optional, 'random': Random(SEED)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'wake/random_int', 'exec'), namespace)
    draw = namespace['random_int']
    cases = [(0, 0), (2**96 - 1, 65535)]
    cases.extend((draw(0, 2**96 - 1, edge_values_prob=0.1), draw(0, 65535, edge_values_prob=0.1))
                 for _ in range(CASES - len(cases)))
    return cases


def review(work, tool, root, forge_tests, target):
    cases = funding_cases(root / tool['path'], tool['commit'])
    fixture = work / 'test/WakeAccounting.t.sol'
    functions = [f'function testWakeCase{i}() public {{ checkBalances({balance}, {profit}); }}'
                 for i, (balance, profit) in enumerate(cases)]
    fixture.write_text("""
pragma solidity ^0.8.24;
import "./NqcFlashFundingExecutor.t.sol";

contract WakeAccountingTest is NqcFlashFundingExecutorTest {
    function checkBalances(uint256 baseline, uint256 profit) internal {
        token.mint(address(executor), baseline);
        strategy.configure(profit + 10, 0, false);
        bytes memory payload = hex"01020304";
        uint256 operatorBefore = token.balanceOf(address(this));
        uint256 realized = executor.execute(_plan(payload, profit), payload);
        _assertEq(realized, profit);
        _assertEq(token.balanceOf(address(executor)), baseline);
        _assertEq(token.balanceOf(address(this)) - operatorBefore, profit);
        _assertEq(token.balanceOf(address(aave)), 707);
        _assertEq(token.balanceOf(address(balancer)), 303);
    }
""" + '\n'.join(functions) + '\n}\n')
    def execute():
        results = forge_tests(work, shutil.which('solc'), '--match-contract', '^WakeAccountingTest$',
                              '--match-test', '^testWakeCase')
        expected = {f'test/WakeAccounting.t.sol:WakeAccountingTest/testWakeCase{i}()' for i in range(len(cases))}
        if results.keys() != expected:
            raise ValueError('Wake/Forge did not execute precisely the generated accounting cases')
        return sum(status == 'Success' for status in results.values())

    passed = execute()
    if passed != len(cases):
        raise ValueError('a Wake/Forge accounting case failed')
    source = work / target
    original = source.read_bytes()
    try:
        shutil.copyfile(work / 'variants/mutants/1' / target, source)
        failed_on_variant = len(cases) - execute()
    finally:
        source.write_bytes(original)
    return {'seed': SEED, 'passed': passed, 'cases_sha256': hashlib.sha256(json.dumps(cases).encode()).hexdigest(),
            'assertions_per_case': 5, 'failed_on_gambit_variant': failed_on_variant}
