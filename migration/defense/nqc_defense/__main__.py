"""Local CLI; deliberately no serve, deploy, broadcast or remote-action command."""

import argparse
import os
from pathlib import Path
import sys

from .codec import Rejected, canonical, decode
from .config import ConfigStore
from .engine import Engine
from .files import create_local, read_local
from .consumer import ArtifactReader


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--configs", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--policy", required=True, help="Pinned SHA3-256 policy digest")
    parser.add_argument("--key-file", type=Path, required=True, help="Private local 32-byte ledger key")
    commands = parser.add_subparsers(dest="command", required=True)
    issue = commands.add_parser("issue")
    issue.add_argument("subject")
    issue.add_argument("asset")
    commands.add_parser("inspect", help="Read a token and request envelope from stdin")
    commands.add_parser("read-json", help="Admit an artifact and parse the exact inspected bytes locally")
    commands.add_parser("checkpoint")
    export = commands.add_parser("export")
    export.add_argument("output", type=Path)
    release = commands.add_parser("release")
    release.add_argument("asset")
    receipt = commands.add_parser("receipt", help="Retrieve and replay a recorded decision locally")
    receipt.add_argument("digest")
    args = parser.parse_args(argv)
    try:
        if args.key_file.lstat().st_mode & 0o077:
            raise Rejected("key_file_permissions")
        key = read_local(args.key_file.parent, args.key_file.name, 32)
        engine = Engine(args.assets, args.configs, args.state, args.policy, key)
        if args.command == "issue":
            result = {"token": engine.issue(args.subject, args.asset)}
        elif args.command in {"inspect", "read-json"}:
            envelope = decode(sys.stdin.buffer.read(65537))
            if type(envelope) is not dict or set(envelope) != {"token", "request"}:
                raise Rejected("envelope")
            if args.command == "inspect":
                result = engine.process(canonical(envelope["request"]), envelope["token"])
            else:
                result = ArtifactReader(engine).read_json(canonical(envelope["request"]), envelope["token"])
        elif args.command == "checkpoint":
            result = engine.checkpoint()
        elif args.command == "export":
            create_local(args.output.parent, args.output.name, engine.export())
            result = {"exported": True}
        elif args.command == "receipt":
            result = engine.receipt(args.digest)
        else:
            result = {"released": engine.release(args.asset)}
        print(canonical(result).decode())
        return 0
    except (Rejected, OSError) as exc:
        print("Local operation rejected: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
