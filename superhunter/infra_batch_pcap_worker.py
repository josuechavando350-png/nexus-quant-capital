"""Read five fixed upstream capture encodings and one intentionally shortened control."""
import hashlib
import io
import json
from pathlib import Path
import resource
import sys

NAMES = ('dhcp.pcap', 'dhcp-nanosecond.pcap', 'dhcp.pcapng', 'dhcp-nanosecond.pcapng',
         'ntp-time.pcap', 'damaged-length.pcap')


def main():
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 9))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))

    def local_only(event, args):
        if event.startswith('socket.') or event in ('os.system', 'subprocess.Popen'):
            raise RuntimeError('offline reader cannot start a process or use a socket')

    sys.addaudithook(local_only)
    sys.path.insert(0, str(Path.cwd() / 'vendor.zip'))
    from scapy.utils import RawPcapReader
    out = {}
    for name in NAMES:
        rows = []
        with RawPcapReader(io.BytesIO(Path(name).read_bytes())) as stream:
            for frame, meta in stream:
                if len(rows) >= 8:
                    raise ValueError('unexpected packet count')
                if hasattr(meta, 'tsresol'):
                    ticks = (meta.tshigh << 32) + meta.tslow
                    epoch, remainder = divmod(ticks * 1_000_000_000, meta.tsresol)
                    if remainder or meta.linktype != 1:
                        raise ValueError('unsupported capture timestamp or link type')
                else:
                    if stream.linktype != 1:
                        raise ValueError('unsupported capture link type')
                    epoch = meta.sec * 1_000_000_000 + meta.usec * (1 if stream.nano else 1000)
                rows.append({'epoch_ns': epoch, 'captured': len(frame), 'wire': meta.wirelen,
                             'frame_sha256': hashlib.sha256(frame).hexdigest()})
        out[name] = rows
    print(json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main()
