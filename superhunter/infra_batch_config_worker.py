"""Read staged disabled workflow text with the Cartography offline parser."""
from pathlib import Path
import json
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (16, 18))
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))

    def restrict(event, args):
        if event.startswith('socket.') or event in ('os.system', 'subprocess.Popen'):
            raise RuntimeError('workflow parsing is offline')

    sys.addaudithook(restrict)
    sys.path.insert(0, str(Path.cwd() / 'libraries.zip'))
    from workflow_parser import parse_workflow_yaml

    result = {}
    for f in sorted(Path.cwd().glob('*.disabled')):
        parsed = parse_workflow_yaml(f.read_text('utf-8'))
        if parsed is None:
            raise ValueError('invalid archived workflow')
        actions = {action.raw_uses: action.is_pinned for action in parsed.actions}
        result[f.name] = {'actions': actions, 'permissions': parsed.permissions, 'jobs': parsed.job_count}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
