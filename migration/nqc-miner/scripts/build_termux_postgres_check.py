#!/usr/bin/env python3
"""Bundle exact repository SQL into an offline Bash runner; no network or server."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render():
    template = (ROOT / 'scripts/termux_postgres_check.template.sh').read_text()
    inputs = {
        'postgres.sql': (ROOT / 'infra/postgres.sql').read_bytes(),
        'cases.sql': (ROOT / 'scripts/postgres_contract_cases.sql').read_bytes(),
    }
    chunks = []
    sums = []
    for index, (name, data) in enumerate(inputs.items()):
        marker = f'NQC_MINER_EMBEDDED_SQL_{index}'
        text = data.decode('utf-8')
        if not text.endswith('\n') or marker in text:
            raise ValueError('unsafe heredoc input')
        chunks.append(f'cat > "$MINER_TEST_EVIDENCE/{name}" <<\'{marker}\'\n{text}{marker}\n')
        sums.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
    chunks.append('cat > "$MINER_TEST_EVIDENCE/input.sha256" <<\'NQC_MINER_INPUT_HASHES\'\n'
                  + ''.join(sums) + 'NQC_MINER_INPUT_HASHES\n')
    cases = inputs['cases.sql'].count(b'SELECT pg_temp.check_ok(') + inputs['cases.sql'].count(b'SELECT pg_temp.reject_sql(')
    return template.replace('__EMBEDDED_SQL__', ''.join(chunks)).replace('__EXPECTED_CASES__', str(cases))


if __name__ == '__main__':
    output = ROOT / 'scripts/nqc-miner-postgres-check.sh'
    output.write_text(render())
    print(output)
