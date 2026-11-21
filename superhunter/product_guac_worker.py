"""Run two pinned GUAC processes on loopback in the caller-created private network."""
import fcntl
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time
from urllib.request import Request, urlopen


def enable_private_loopback(parent_net):
    if os.stat('/proc/self/ns/net').st_ino == parent_net:
        raise RuntimeError('missing private network')
    # /sys may reflect the mounting namespace; /proc/net/dev describes this network.
    interfaces = [line.split(':')[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]]
    if interfaces != ['lo']:
        raise RuntimeError('unexpected interface in private network')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        current = fcntl.ioctl(control, 0x8913, struct.pack('16sH22x', b'lo', 0))
        flags = struct.unpack_from('H', current, 16)[0]
        fcntl.ioctl(control, 0x8914, struct.pack('16sH22x', b'lo', flags | 1))



def collect(parent_net):
    enable_private_loopback(parent_net)
    endpoint = 'http://127.0.0.1:8080/query'
    server = subprocess.Popen(['./guacgql', '--gql-backend', 'keyvalue', '--kv-store', 'memmap'],
                              stdout=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError('GUAC exited during startup')
            try:
                with socket.create_connection(('127.0.0.1', 8080), timeout=.2):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('GUAC startup timed out')
        subprocess.run(['./guacone', 'collect', 'files', '--gql-addr', endpoint, 'docs'],
                       check=True, stdout=subprocess.DEVNULL, timeout=60)
        fields = 'type namespaces { namespace names { versions { purl } } }'
        query = ('{ IsDependency(isDependencySpec:{}) { origin justification dependencyType package { '
                 + fields + ' } dependencyPackage { ' + fields + ' } } }')
        req = Request(endpoint, data=json.dumps({'query': query}).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=10) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise RuntimeError('GUAC response exceeds evidence limit')
        sys.stdout.buffer.write(raw)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == '__main__':
    collect(int(sys.argv[1]))
