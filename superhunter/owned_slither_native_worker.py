"""Run only one fixed OWNED Slither control with checked files and socket denial."""
import json
import os
from pathlib import Path
import resource
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from superhunter import quality, native_compile, slither_owned_worker as previous
from superhunter import owned_slither_dependencies as dependencies, owned_slither_network as network
from superhunter.owned_slither_cases import SOURCES, WORKER_POLICY
from superhunter.safe_io import canonical


def main(argv: list[str]) -> int:
    try:
        if len(argv)!=3: return 2
        root,mode,digest = Path(argv[0]),argv[1],argv[2]
        if (mode not in SOURCES or not root.is_absolute() or not root.is_dir() or
                root.resolve()!=root or dependencies.sha(canonical(quality.source_snapshot()))!=digest):
            return 2
        if (previous._file_sha256(root/'Owned.sol',4096)!=dependencies.sha(SOURCES[mode]) or
                previous._file_sha256(root/'solc',64_000_000)!=native_compile.PIN['sha256']):
            return 2
        identity = dependencies.verify_dependencies()
        # No scanner import precedes this filter.
        proof = network.install()
        os.umask(0o077)
        resource.setrlimit(resource.RLIMIT_CPU,(WORKER_POLICY['cpu_seconds'],)*2)
        resource.setrlimit(resource.RLIMIT_AS,(WORKER_POLICY['address_space_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(WORKER_POLICY['file_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_NOFILE,(WORKER_POLICY['open_files'],)*2)
        admission = {'schema_version':1,'mode':mode,'source_digest':digest,
                     'source_sha256':dependencies.sha(SOURCES[mode]),
                     'dependencies':identity,'network':proof,'worker_policy':WORKER_POLICY}
        fd = os.open(root/'admission.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(canonical(admission));stream.flush();os.fsync(stream.fileno())
        cache = root/'private-bytecode-cache';cache.mkdir(mode=0o700,exist_ok=False)
        os.chdir(root)
        command = [sys.executable,'-I','-B','-X','pycache_prefix='+str(cache),'-m','slither',
                   'Owned.sol','--solc',str(root/'solc'),'--detect','tx-origin',
                   '--fail-none','--disable-color','--json','slither.json']
        os.execv(sys.executable,command)
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError):
        return 2
    return 2


if __name__=='__main__':
    raise SystemExit(main(sys.argv[1:]))
