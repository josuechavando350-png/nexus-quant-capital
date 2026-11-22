"""Join a T36 session at the query boundary of the original 200-project product."""
from contextvars import ContextVar
from pathlib import Path

from .privacy import PrivateArgumentParser
from .product_reasoning import EvidenceError

_runtime = ContextVar('t36_toolkit_runtime', default=None)


class ToolkitIndex:
    def __init__(self, base):
        self.base = base
        self.repos = base.repos
        self.rows = {}
        self.session = None

    def attach_toolkit(self, session):
        rows = {row['repository'].casefold(): row for row in session['repositories']}
        if len(rows) != len(session['repositories']):
            raise EvidenceError('duplicate toolkit identity')
        historical = {key: row['catalog_id'] for key, row in rows.items() if 'catalog_id' in row}
        if historical != {key: row['catalog_id'] for key, row in self.repos.items()}:
            raise EvidenceError('toolkit historical identities differ from this product bundle')
        lookups = rows.copy()
        for row in rows.values():
            for alias in row.get('aliases', []):
                if alias.casefold() in lookups:
                    raise EvidenceError('duplicate toolkit alias')
                lookups[alias.casefold()] = row
        self.rows, self.session = lookups, session

    def lookup(self, query):
        key = query.strip().casefold()
        if key == 'toolkit-matrix':
            if self.session is None:
                raise EvidenceError('toolkit-matrix requires --toolkit-runtime')
            return self.session
        if key == 'integration-matrix' and self.session is not None:
            return {**self.base.lookup(key), 'toolkit_session': self.session}
        if key in self.rows:
            joined = self.rows[key]
            return {**(self.base.lookup(joined['repository']) or {}), **joined}
        return self.base.lookup(query)


def for_queries(base):
    index = ToolkitIndex(base)
    runtime = _runtime.get()
    if runtime is not None:
        from .toolkit import run_session
        index.attach_toolkit(run_session(runtime, [])['product_session'])
    return index


def main(argv):
    from .product_review import main as review
    parser = PrivateArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--toolkit-runtime', type=Path)
    options, remaining = parser.parse_known_args(argv[1:])
    if '--help' in remaining or '-h' in remaining:
        print('  --toolkit-runtime DIR   run the fixed T36 session and enable toolkit-matrix')
    token = _runtime.set(options.toolkit_runtime)
    try:
        return review([argv[0], *remaining])
    finally:
        _runtime.reset(token)
