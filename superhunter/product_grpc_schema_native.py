"""Inspect fixed OWNED gRPC schemas with a pinned grpcurl build, without a server."""
from pathlib import Path
import subprocess
import tempfile

from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import canonical, read_artifact, strict_json

REPOSITORIES = {'fullstorydev/grpcurl': 'executable'}
PINS = 'superhunter/product_supply/grpc-schema-native-pins.json'
PINS_SHA = '83fe24f00ff7c01765048984849e9c5016e1b7c17f57d123b2ac727f2a88f3b4'
CASES = 'superhunter/product_supply/grpc-schema-native-owned.json'
ISOLATE = ('/usr/bin/unshare', '--user', '--map-current-user', '--net')
_MISSING = object()


def inputs():
    raw = read_artifact(ROOT, PINS)
    if sha(raw) != PINS_SHA:
        raise EvidenceError('gRPC schema producer pins differ from reviewed artifacts')
    pins = strict_json(raw)
    cases = read_artifact(ROOT, CASES)
    if sha(cases) != pins['cases_sha256']:
        raise EvidenceError('OWNED gRPC schema controls differ')
    return pins, strict_json(cases)


def wire_fields(data, rules, repeated=()):
    """Read only bounded wire types 0 and 2 used by these descriptor controls."""
    if type(data) is not bytes or not data or len(data) > 65536:
        raise EvidenceError('descriptor bytes are missing or exceed the owned bound')
    offset, fields = 0, {}

    def varint():
        nonlocal offset
        value = 0
        for count in range(10):
            if offset >= len(data):
                raise EvidenceError('truncated descriptor integer')
            byte = data[offset]
            offset += 1
            if count == 9 and byte > 1:
                raise EvidenceError('descriptor integer exceeds uint64')
            value |= (byte & 127) << (count * 7)
            if byte < 128:
                if count and byte == 0:
                    raise EvidenceError('noncanonical descriptor integer')
                return value
        raise EvidenceError('descriptor integer exceeds its byte bound')

    count = 0
    while offset < len(data):
        count += 1
        if count > 128:
            raise EvidenceError('too many descriptor fields')
        tag = varint()
        number, wire = tag >> 3, tag & 7
        if number not in rules or wire != rules[number]:
            raise EvidenceError('unexpected descriptor field or wire type')
        if number in fields and number not in repeated:
            raise EvidenceError('duplicate singular descriptor field')
        if wire == 0:
            value = varint()
        elif wire == 2:
            size = varint()
            if size > len(data) - offset:
                raise EvidenceError('truncated descriptor payload')
            value = data[offset:offset + size]
            offset += size
        else:
            raise EvidenceError('unsupported descriptor wire type')
        fields.setdefault(number, []).append(value)
    return fields


def one(fields, number, default=_MISSING):
    values = fields.get(number, [])
    if not values and default is not _MISSING:
        return default
    if len(values) != 1:
        raise EvidenceError('missing or repeated required descriptor field')
    return values[0]


def schema_from_descriptor(raw):
    """Independent limited decoder; this is not a general protobuf validator."""
    try:
        envelope = wire_fields(raw, {1: 2})
        file = wire_fields(one(envelope, 1), {1: 2, 2: 2, 4: 2, 6: 2, 9: 2, 12: 2}, (4, 6))
        text = lambda fields, number: one(fields, number).decode('ascii')
        package = text(file, 2)
        messages, services = {}, {}
        for encoded in file.get(4, []):
            message = wire_fields(encoded, {1: 2, 2: 2}, (2,))
            name = package + '.' + text(message, 1)
            if name in messages:
                raise EvidenceError('duplicate descriptor message identity')
            fields, numbers, names = [], set(), set()
            for encoded_field in message.get(2, []):
                field = wire_fields(encoded_field, {1: 2, 3: 0, 4: 0, 5: 0, 10: 2})
                number, label, kind = one(field, 3), one(field, 4), one(field, 5)
                field_name = text(field, 1)
                if (number < 1 or number > 536870911 or number in numbers or field_name in names or
                        label != 1 or kind not in (4, 9)):
                    raise EvidenceError('descriptor scalar field differs from the bounded grammar')
                numbers.add(number)
                names.add(field_name)
                fields.append({'number': number, 'name': field_name, 'json_name': text(field, 10),
                               'type': {4: 'uint64', 9: 'string'}[kind], 'wire_type': {4: 0, 9: 2}[kind]})
            messages[name] = sorted(fields, key=lambda f: f['number'])
        for encoded in file.get(6, []):
            service = wire_fields(encoded, {1: 2, 2: 2}, (2,))
            name = package + '.' + text(service, 1)
            if name in services:
                raise EvidenceError('duplicate descriptor service identity')
            methods = {}
            for encoded_method in service.get(2, []):
                method = wire_fields(encoded_method, {1: 2, 2: 2, 3: 2, 5: 0, 6: 0})
                method_name = text(method, 1)
                incoming, outgoing = text(method, 2), text(method, 3)
                client, server = one(method, 5, 0), one(method, 6, 0)
                if (method_name in methods or incoming.removeprefix('.') not in messages or
                        outgoing.removeprefix('.') not in messages or client not in (0, 1) or server not in (0, 1)):
                    raise EvidenceError('descriptor method identity, type or streaming flag differs')
                methods[method_name] = {'input': incoming, 'output': outgoing,
                                        'client_streaming': bool(client), 'server_streaming': bool(server)}
            services[name] = methods
        return {'file': text(file, 1), 'package': package, 'syntax': text(file, 12),
                'messages': messages, 'services': services}
    except (UnicodeDecodeError, KeyError, TypeError) as error:
        raise EvidenceError('malformed OWNED descriptor structure') from error


def views_from_schema(schema):
    """Render the accepted descriptor subset independently of grpcurl's text printer."""
    service, = schema['services']
    methods = schema['services'][service]
    rendered = [service + ' is a service:', 'service ' + service.rsplit('.', 1)[1] + ' {']
    for name, method in sorted(methods.items()):
        request = ('stream ' if method['client_streaming'] else '') + method['input']
        response = ('stream ' if method['server_streaming'] else '') + method['output']
        rendered.append('  rpc ' + name + ' ( ' + request + ' ) returns ( ' + response + ' );')
    rendered.append('}')
    views = {'services': (service + '\n').encode(),
             'methods': ''.join(service + '.' + name + '\n' for name in sorted(methods)).encode(),
             'service': ('\n'.join(rendered) + '\n').encode()}
    for label, name in [('request', 'nqc.owned.BalanceRequest'), ('reply', 'nqc.owned.BalanceReply')]:
        rows = [name + ' is a message:', 'message ' + name.rsplit('.', 1)[1] + ' {']
        rows.extend('  ' + field['type'] + ' ' + field['name'] + ' = ' + str(field['number']) + ';'
                    for field in schema['messages'][name])
        rows.append('}')
        views[label] = ('\n'.join(rows) + '\n').encode()
    return views


def validate_case(name, source, descriptor, views, protoset_views, pins, cases):
    wanted = pins['cases'][name]
    if sha(source) != wanted['source_sha256'] or sha(descriptor) != wanted['descriptor_sha256']:
        raise EvidenceError('native descriptor or OWNED source differs from the reviewed case')
    schema = schema_from_descriptor(descriptor)
    if canonical(schema) != canonical(cases['expected_schemas'][name]):
        raise EvidenceError('native descriptor differs from the independent OWNED schema witness')
    expected_views = views_from_schema(schema)
    if views != expected_views or protoset_views != expected_views:
        raise EvidenceError('gRPC list/describe text disagrees with its decoded descriptor')
    return {'source_sha256': sha(source), 'descriptor_sha256': sha(descriptor),
            'descriptor_bytes': len(descriptor), 'schema': schema,
            'views_sha256': {label: sha(value) for label, value in sorted(views.items())},
            'protoset_replay_views_matched': len(expected_views)}


def schema_changes(before, after):
    def methods(schema):
        return {service + '.' + name: definition for service, values in schema['services'].items()
                for name, definition in values.items()}
    def fields(schema):
        return {(message, field['number']): field for message, values in schema['messages'].items() for field in values}
    old_methods, new_methods = methods(before), methods(after)
    old_fields, new_fields = fields(before), fields(after)
    changed_methods = [{'method': name, 'before': old_methods[name], 'after': new_methods[name]}
                       for name in sorted(old_methods.keys() & new_methods.keys())
                       if old_methods[name] != new_methods[name]]
    changed_fields = [{'message': key[0], 'number': key[1], 'before': old_fields[key], 'after': new_fields[key]}
                      for key in sorted(old_fields.keys() & new_fields.keys()) if old_fields[key] != new_fields[key]]
    return {'removed_methods': sorted(old_methods.keys() - new_methods.keys()),
            'added_methods': sorted(new_methods.keys() - old_methods.keys()),
            'changed_methods': changed_methods, 'changed_fields': changed_fields}


def validate_rejection(proc, expected):
    if (type(proc.returncode) is not int or proc.returncode != 1 or proc.stdout or
            sha(proc.stderr) != expected['stderr_sha256']):
        raise EvidenceError('invalid OWNED gRPC control was not rejected for its expected reason')
    return {'rejected': True, 'exit_code': 1, 'stderr_sha256': sha(proc.stderr), 'reason': expected['reason']}


def run(kit):
    """Only fixed list/describe commands over owned files; no server or RPC target parameter."""
    pins, cases = inputs()
    results, rejected = {}, {}
    with tempfile.TemporaryDirectory(prefix='nqc-grpc-schema-') as temporary:
        root = Path(temporary)
        for name, artifact in pins['files'].items():
            copy_release(name, Path(kit)/name, root/name, artifact['sha256'],
                         limit=artifact['bytes'], executable=artifact['executable'])
        env = {'HOME': temporary, 'TMPDIR': temporary, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'GOMAXPROCS': '2'}

        def execute(work, mode, arguments):
            selector = ['-proto', 'schema.proto'] if mode == 'source' else ['-protoset', 'schema.pb']
            proc = subprocess.run([*ISOLATE, str(root/'grpcurl'), '-use-reflection=false', *selector, *arguments],
                                  cwd=work, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
            if len(proc.stdout) > 65536 or len(proc.stderr) > 65536:
                raise EvidenceError('gRPC schema producer output exceeds the owned bound')
            return proc

        commands = [('services', ['list']), ('methods', ['list', cases['service']]),
                    ('service', ['describe', cases['service']]),
                    ('request', ['describe', cases['messages'][0]]),
                    ('reply', ['describe', cases['messages'][1]])]
        for name in ('base', 'changed'):
            work = root/name
            work.mkdir()
            source = cases['schemas'][name].encode()
            (work/'schema.proto').write_bytes(source)
            collected = {}
            for mode in ('source', 'protoset'):
                collected[mode] = {}
                for label, arguments in commands:
                    args = ['-protoset-out', 'schema.pb', *arguments] if mode == 'source' and label == 'services' else arguments
                    proc = execute(work, mode, args)
                    if proc.returncode != 0 or proc.stderr:
                        raise EvidenceError('fixed gRPC schema list/describe control failed')
                    collected[mode][label] = proc.stdout
            descriptor = read_artifact(work, 'schema.pb')
            results[name] = validate_case(name, source, descriptor, collected['source'], collected['protoset'], pins, cases)
            missing = execute(work, 'source', ['describe', cases['unknown_symbol']])
            rejected[name + '_unknown_symbol'] = validate_rejection(missing, pins['rejections']['unknown_symbol'])
            if (work/'schema.proto').read_bytes() != source:
                raise EvidenceError('gRPC inspection changed the OWNED source')
        for name, source in cases['invalid_schemas'].items():
            work = root/name
            work.mkdir()
            (work/'schema.proto').write_text(source)
            rejected[name] = validate_rejection(execute(work, 'source', ['list']), pins['rejections'][name])
    changes = schema_changes(results['base']['schema'], results['changed']['schema'])
    if canonical(changes) != canonical(cases['expected_changes']):
        raise EvidenceError('OWNED gRPC method/type changes differ from the independent witness')
    return {'schema_version': 1, 'query': 'grpc-schema-native', 'repository': pins['repository'],
            'revision': pins['revision'], 'version': pins['version'], 'producer_kind': pins['producer_kind'],
            'producer_sha256': pins['files']['grpcurl']['sha256'], 'pins_sha256': PINS_SHA,
            'cases_sha256': pins['cases_sha256'], 'cases': results, 'changes': changes,
            'rejected_controls': rejected,
            'summary': {'valid_schemas': 2, 'source_views_checked': 10, 'protoset_views_checked': 10,
                        'invalid_schemas_rejected': 2, 'unknown_symbols_rejected': 2,
                        'removed_methods': len(changes['removed_methods']), 'added_methods': len(changes['added_methods']),
                        'changed_method_signatures': len(changes['changed_methods']),
                        'changed_field_types': len(changes['changed_fields'])},
            'scope': 'fixed OWNED proto3 list/describe; no server, connection or RPC invocation',
            'limitations': ['two fixed schemas and two malformed derivatives; not general protobuf validation',
                           'schema changes do not establish authorization behavior or vulnerabilities',
                           'protoset replay uses the same grpcurl build; the bounded descriptor decoder is independently implemented',
                           'network namespaces restrict networking but are not a complete filesystem or syscall sandbox'],
            'original_vulnerabilities_confirmed': 0}
