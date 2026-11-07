"""Closed, separately installed wheel inventory for the three OWNED sources.

The isolated layout preserves conflicting documentation shipped by different
distributions. No package code is imported during this byte check.
"""
import hashlib
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import platform
import stat
import sys

from .owned_slither_pins import PINS
from .safe_io import canonical

PROFILE = 'owned-slither-separated-wheels-v1'
MAX_ENTRIES, MAX_FILE, MAX_BYTES = 8192, 32_000_000, 128_000_000


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def bootstrap_bytes() -> bytes:
    return (''.join('owned_distributions/'+pin['directory']+'\n'
                    for _,pin in sorted(PINS.items(),key=lambda item:item[0].lower()))).encode()


def expected_identity() -> dict:
    return {'profile':PROFILE, 'distribution_count':len(PINS),
            'wheel_derived_files':sum(pin['files'] for pin in PINS.values()),
            'pins_sha256':sha(canonical(PINS)), 'bootstrap_sha256':sha(bootstrap_bytes()),
            'producer_authenticated':False, 'process_memory_integrity_proved':False}


def _read(path: Path, budget: list[int]) -> bytes:
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE,
             'SLITHER_DEPENDENCY_FILE')
        budget[0] += before.st_size
        need(budget[0] <= MAX_BYTES,'SLITHER_DEPENDENCY_BYTE_BUDGET')
        with os.fdopen(fd,'rb',closefd=False) as stream:
            raw = stream.read(MAX_FILE+1)
        after = os.fstat(fd)
        need(len(raw)==before.st_size and
             (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
             (after.st_size,after.st_mtime_ns,after.st_ctime_ns),'SLITHER_DEPENDENCY_CHANGED')
        return raw
    finally:
        os.close(fd)


def _distribution_inventory(root: Path, pin: dict, budget: list[int], seen: list[int]) -> dict:
    hashes = {}
    excluded = {pin['metadata_directory']+'/'+name for name in ('RECORD','INSTALLER','REQUESTED')}
    def walk(path: Path) -> None:
        seen[0] += 1
        need(seen[0] <= MAX_ENTRIES,'SLITHER_DEPENDENCY_ENTRY_BUDGET')
        info = path.lstat(); relative = path.relative_to(root)
        need(not stat.S_ISLNK(info.st_mode) and len(relative.parts)<=20,
             'SLITHER_DEPENDENCY_SYMLINK_OR_DEPTH')
        if stat.S_ISDIR(info.st_mode):
            if relative.as_posix() == 'bin':
                return  # pip-generated launchers; fixed workers use python -m.
            for child in path.iterdir(): walk(child)
            return
        need(stat.S_ISREG(info.st_mode),'SLITHER_DEPENDENCY_FILE')
        if '__pycache__' in relative.parts:
            need(path.suffix=='.pyc','SLITHER_DEPENDENCY_CACHE_PAYLOAD'); return
        if relative.as_posix() in excluded:
            need(info.st_size<=2_000_000,'SLITHER_DEPENDENCY_INSTALL_METADATA_BUDGET'); return
        hashes[relative.as_posix()] = sha(_read(path,budget))
    walk(root)
    # Wheel-derived inventory pins use compact JSON without a trailing newline.
    digest = sha(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode())
    need(len(hashes)==pin['files'] and digest==pin['inventory_sha256'],
         'SLITHER_DEPENDENCY_BYTES')
    return hashes


def verify_dependencies() -> dict:
    need(platform.system()=='Linux' and platform.machine()=='x86_64' and
         sys.version_info[:2]==(3,12),'SLITHER_DEPENDENCY_PLATFORM')
    site = Path(sys.prefix)/'lib/python3.12/site-packages'
    need(site.is_dir() and site.resolve()==site,'SLITHER_DEPENDENCY_SITE')
    need({p.name for p in site.iterdir()}=={'owned_distributions','superhunter_owned_distributions.pth'},
         'SLITHER_DEPENDENCY_SITE_INVENTORY')
    separated = site/'owned_distributions'
    need(separated.is_dir() and not separated.is_symlink() and
         {p.name for p in separated.iterdir()}=={pin['directory'] for pin in PINS.values()},
         'SLITHER_DEPENDENCY_DISTRIBUTION_INVENTORY')
    bootstrap = site/'superhunter_owned_distributions.pth'
    need(_read(bootstrap,[0])==bootstrap_bytes(),'SLITHER_DEPENDENCY_BOOTSTRAP')
    snapshots = {}
    for pass_index in range(2):
        budget,seen = [0],[0]
        for name,pin in sorted(PINS.items()):
            dist = distribution(name);root = separated/pin['directory']
            need(dist.version==pin['version'] and Path(dist.locate_file(''))==root and
                 root.is_dir() and not root.is_symlink(),'SLITHER_DEPENDENCY_IDENTITY')
            found = _distribution_inventory(root,pin,budget,seen)
            if pass_index==0: snapshots[name]=found
            else: need(found==snapshots[name],'SLITHER_DEPENDENCY_CHANGED')
    need(_read(bootstrap,[0])==bootstrap_bytes(),'SLITHER_DEPENDENCY_BOOTSTRAP_CHANGED')
    return expected_identity()
