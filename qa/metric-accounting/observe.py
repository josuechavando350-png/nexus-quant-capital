"""Compile and execute only this benchmark's fixed, nonmonetary worksheet fixtures."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
FIELDS = ("left", "right", "rows", "total")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def collect(tools, vectors, reverse=False):
    source = (HERE / "Sheets.sol").read_bytes()
    names = re.findall(r"^contract (S[0-9a-f]{8}) is Sheet", source.decode(), re.M)
    if len(names) != 12 or len(set(names)) != 12:
        raise ValueError("wrong fixed worksheet inventory")
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "src").mkdir()
        (root / "test").mkdir()
        (root / "src/Sheets.sol").write_bytes(source)
        (root / "foundry.toml").write_text('[profile.default]\nevm_version="paris"\noffline=true\n')
        driver = ['// SPDX-License-Identifier: MIT', 'pragma solidity 0.8.30;',
                  'import "../src/Sheets.sol";', 'contract Observe {',
                  'event log_named_uint(string key, uint value);',
                  'function row(uint i, Sheet sheet, uint l, uint r, uint a, uint b) private {',
                  '(uint left, uint right, uint rows, uint total) = sheet.report(l,r,a,b);',
                  'emit log_named_uint("i",i);']
        driver.extend(f'emit log_named_uint("{field}",{field});' for field in FIELDS)
        driver.append('}')
        for name in names:
            driver.append(f'function test_{name}() public {{ Sheet sheet = new {name}();')
            for i in sorted(range(len(vectors)), reverse=reverse):
                args = ','.join(str(x) for x in vectors[i])
                driver.append(f'row({i},sheet,{args});')
            driver.append('}')
        driver.append('}')
        (root / "test/Observe.t.sol").write_text('\n'.join(driver))
        proc = subprocess.run([tools / "forge", "test", "--offline", "--root", root, "--use", tools / "solc",
                               "--match-contract", "Observe", "--json", "-vv"], cwd=root,
                              env={"PATH": "/usr/bin:/bin", "HOME": temp, "TMPDIR": temp,
                                   "LC_ALL": "C", "FOUNDRY_DISABLE_NIGHTLY_WARNING":"1"},
                              capture_output=True, timeout=120)
        if proc.returncode:
            raise ValueError("fixed Solidity worksheet run failed: " + (proc.stderr + proc.stdout)[-1500:].decode())
        result = json.loads(proc.stdout)
        tests = result["test/Observe.t.sol:Observe"]["test_results"]
        if set(tests) != {f"test_{name}()" for name in names}:
            raise ValueError("missing or extra worksheet")
        observations = {}
        for name in names:
            test = tests[f"test_{name}()"]
            logs = test["decoded_logs"]
            if test["status"] != "Success" or len(logs) != 5 * len(vectors):
                raise ValueError(f"incomplete native observations for {name}: {str(logs)[:240]}")
            rows = {}
            for start in range(0, len(logs), 5):
                values = {}
                for field, item in zip(("i", *FIELDS), logs[start:start + 5], strict=True):
                    match = re.fullmatch(re.escape(field) + r": ([0-9]+)(?: \[.*\])?", item)
                    if not match:
                        raise ValueError(f"unexpected numeric field: {item}")
                    values[field] = int(match[1])
                index = values.pop("i")
                if index in rows:
                    raise ValueError("duplicate worksheet observation")
                rows[index] = values
            observations[name] = [rows[i] for i in range(len(vectors))]
        return observations
