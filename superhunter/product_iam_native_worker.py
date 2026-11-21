"""Execute Policy Sentry APIs over fixed local policy controls supplied by the parent."""
import json
from pathlib import Path
import sys


def main():
    work = Path.cwd()
    sys.path.insert(0, str(work/'lib'))
    def audit(event, args):
        if event.startswith('socket.'):
            raise RuntimeError('IAM controls do not open sockets')
    sys.addaudithook(audit)
    from policy_sentry.analysis.analyze import analyze_by_access_level
    from policy_sentry.analysis.expand import get_expanded_policy
    from policy_sentry.querying.actions import get_action_data
    from policy_sentry.bin.version import __version__
    payload = json.load(sys.stdin)
    result = {}
    for name, policy in payload['policies'].items():
        expanded = get_expanded_policy(policy)
        observations = {level: sorted(analyze_by_access_level(policy, level))
                        for level in ('Read', 'Write', 'Permissions management')}
        actions = sorted(set(action for statement in expanded['Statement']
                             for action in statement['Action']))
        unknown = [action for action in actions if not get_action_data(*action.split(':'))]
        result[name] = {'expanded': expanded, 'access_levels': observations, 'unknown_actions': unknown}
    (work/'iam-native.json').write_text(json.dumps({'version': __version__, 'cases': result}, sort_keys=True))


if __name__ == '__main__':
    main()
