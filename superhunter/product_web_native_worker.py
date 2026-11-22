"""Offline producer for an owned WSGI contract and captured HTTP packet fixtures."""
import base64
from io import BytesIO
import json
import logging
from pathlib import Path
import re
import sys
import struct
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path('lib').resolve()))

import scapy
from scapy.packet import Packet
from scapy.fields import ByteField, ShortField, IntField, IPField, MACField, StrField
from scapy.utils import RawPcapReader, checksum
from scapy.error import log_runtime
import schemathesis
from schemathesis.core.failures import FailureGroup
from importlib.metadata import version


class OwnedFrame(Packet):
    """The fixed Ethernet/IPv4/TCP layout used by this owned capture.

    Scapy's generic native parser needs no network interface discovery. Explicit
    fields avoid importing its live socket modules in a socket-free sandbox.
    Options, other EtherTypes and fragmented frames are outside this fixture.
    """
    fields_desc = [MACField('destination_mac', None), MACField('source_mac', None),
                   ShortField('ether_type', 0x0800), ByteField('version_ihl', 0x45),
                   ByteField('tos', 0), ShortField('ip_length', 0), ShortField('ip_id', 0),
                   ShortField('ip_fragment', 0), ByteField('ttl', 64), ByteField('protocol', 6),
                   ShortField('ip_checksum', 0), IPField('source_ip', None), IPField('destination_ip', None),
                   ShortField('source_port', 0), ShortField('destination_port', 0),
                   IntField('sequence', 0), IntField('acknowledgment', 0),
                   ByteField('tcp_offset', 0x50), ByteField('tcp_flags', 0),
                   ShortField('window', 0), ShortField('tcp_checksum', 0),
                   ShortField('urgent', 0), StrField('http', b'')]


def api_checks(payload):
    schema = schemathesis.openapi.from_dict(payload['openapi'])
    operation = schema['/catalog/{id}']['get']
    trials = []
    for trial in payload['trials']:
        body = json.dumps(trial['body'], sort_keys=True, separators=(',', ':')).encode()

        def app(environ, start_response):
            if environ['REQUEST_METHOD'] != 'GET' or environ['PATH_INFO'] != '/catalog/' + str(trial['id']):
                raise ValueError('request escaped the owned fixture')
            start_response(str(trial['status']) + (' OK' if trial['status'] == 200 else ' Internal Server Error'),
                           [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))])
            return [body]

        case = operation.Case(path_parameters={'id': trial['id']})
        response = case.call(app=app)
        failures = []
        try:
            case.validate_response(response)
        except FailureGroup as group:
            failures = sorted(type(error).__name__ for error in group.exceptions)
        trials.append({'id': trial['id'], 'mutation': trial['mutation'], 'status': response.status_code,
                       'body': json.loads(response.content), 'valid': not failures, 'failure_types': failures})
    return trials


def packet_rows(encoded):
    rows = []
    with RawPcapReader(BytesIO(base64.b64decode(encoded, validate=True))) as capture:
        for raw, metadata in capture:
            packet = OwnedFrame(raw)
            if (packet.ether_type, packet.version_ihl, packet.ip_fragment, packet.protocol,
                    packet.tcp_offset) != (0x0800, 0x45, 0, 6, 0x50):
                raise ValueError('capture is outside the explicit owned Ethernet/IPv4/TCP layout')
            payload = packet.http
            head, body = payload.split(b'\r\n\r\n', 1)
            lines = head.split(b'\r\n')
            headers = dict(line.decode('ascii').split(': ', 1) for line in lines[1:])
            pseudo = raw[26:34] + struct.pack('!BBH', 0, 6, packet.ip_length - 20)
            rows.append({'src': packet.source_ip, 'dst': packet.destination_ip,
                         'sport': packet.source_port, 'dport': packet.destination_port,
                         'captured_length': len(raw), 'wire_length': metadata.wirelen,
                         'ip_length': packet.ip_length, 'server': headers['Server'],
                         'ip_checksum_valid': checksum(raw[14:34]) == 0,
                         'tcp_checksum_valid': checksum(pseudo + raw[34:]) == 0,
                         'content_length': int(headers['Content-Length']),
                         'body_hex': body.hex(), 'status_line': lines[0].decode('ascii')})
    return rows


def fingerprints(rows):
    selected = {'Apache', 'nginx with version info and/or mods'}
    nodes = [node for node in ET.parse('http_servers.xml').getroot().findall('fingerprint')
             if node.findtext('description') in selected]
    if len(nodes) != 2:
        raise ValueError('reviewed fingerprint patterns are missing or ambiguous')
    observations = []
    for row in rows:
        matches = []
        for node in nodes:
            match = re.match(node.attrib['pattern'], row['server'])
            if match:
                params = {}
                for param in node.findall('param'):
                    key, position = param.attrib['name'], int(param.attrib['pos'])
                    if key in ('service.product', 'service.version'):
                        params[key] = match.group(position) if position else param.attrib['value']
                matches.append({'rule': node.findtext('description'), 'parameters': params})
        observations.append({'banner': row['server'], 'matches': matches})
    return observations


def main():
    data = sys.stdin.buffer.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('owned fixture too large')
    payload = json.loads(data)
    packets, warnings = {}, {}

    class CaptureWarnings(logging.Handler):
        def emit(self, record):
            warnings[name].append({'level': record.levelname, 'message': record.getMessage()})

    handler = CaptureWarnings()
    log_runtime.addHandler(handler)
    try:
        for name, value in payload['captures'].items():
            warnings[name] = []
            packets[name] = packet_rows(value)
    finally:
        log_runtime.removeHandler(handler)
    result = {'api_trials': api_checks(payload), 'captures': packets,
              'capture_warnings': warnings,
              'fingerprints': fingerprints(packets['complete']),
              'versions': {'schemathesis': version('schemathesis'), 'scapy': scapy.VERSION}}
    Path('web-native.json').write_text(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
