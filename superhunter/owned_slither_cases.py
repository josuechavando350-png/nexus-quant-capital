"""Three immutable detector controls; no external or caller-supplied sources."""
import hashlib
from pathlib import Path
from . import slither_owned_runner as positive, slither_control_pair as pair
from .safe_io import read_artifact

SOURCES = {'positive':positive.OWNED_SOURCE, 'clean':pair.CLEAN_SOURCE,
           'comparison':pair.COMPARISON_SOURCE}
SCOPES = {'positive':'owned-fixed-local-fixture', 'clean':'owned-fixed-local-fixture-clean',
          'comparison':'owned-fixed-local-fixture-comparison'}
FIXTURE_COMMIT = 'b18b23128a601498a3dba8fc0bfcbbd2eb726934'
FIXTURE_REPOSITORY = 'josuechavando350-png/nexus-quant-capital'
SOURCE_PINS = {
    'positive':'ef5475a13e367bef34010e339c082c85383ab85e4f229cd607899f5f52ce0c64',
    'clean':'f4435d614ec0d890f56f06c6250bba4a60152255fa3f8d5ceec13952f9aba0f1',
    'comparison':'45e77d6d43ee7a13720323e48ed103e64447013c705af58f53e824ae3807df92'}
CONTAINER_PINS = {
    'slither_owned_runner.py':{'git_blob':'0a37fb11dd1bf43ff56dcbe84ceb0b1eb6da3051',
        'sha256':'a370b4f1343dcf814bbba112d662f5755f7e8747953b4f4adba843037b21237b'},
    'slither_control_pair.py':{'git_blob':'cb085a3958185194948df64e401bf47c3b287034',
        'sha256':'b8349c806601ab18d409ab4971ed8111616806f3d82dd5be1df2b0e48dd3b6be'}}
WORKER_POLICY = {'wall_seconds':90,'cpu_seconds':35,'address_space_bytes':2*1024**3,
                 'file_bytes':2_000_000,'open_files':96}


def fixture_provenance() -> dict:
    """Check the original containers and extracted literals; no remote lookup."""
    if {mode:hashlib.sha256(raw).hexdigest() for mode,raw in SOURCES.items()}!=SOURCE_PINS:
        raise ValueError('OWNED_SLITHER_ORIGINAL_LITERAL_CHANGED')
    for name,pin in CONTAINER_PINS.items():
        raw=read_artifact(Path(__file__).resolve().parent,name)
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if hashlib.sha256(raw).hexdigest()!=pin['sha256'] or blob!=pin['git_blob']:
            raise ValueError('OWNED_SLITHER_ORIGINAL_CONTAINER_CHANGED')
    return {'repository':FIXTURE_REPOSITORY,'commit':FIXTURE_COMMIT,
            'container_files':{'superhunter/'+name:dict(pin) for name,pin in CONTAINER_PINS.items()},
            'generated_source_sha256':dict(SOURCE_PINS),'generated_source_is_tracked_repository_file':False,
            'repository_commit_membership_authenticated_at_runtime':False}


def context(mode: str, normalized_sha256: str) -> dict:
    return {'schema_version':1, 'scope_id':SCOPES[mode],
            'repository':{'repo':FIXTURE_REPOSITORY,'commit':FIXTURE_COMMIT},
            'tool':{'name':'slither','version':positive.SCANNER_VERSION},
            'detectors':[positive.DETECTOR], 'report_sha256':normalized_sha256,
            'sources':{'Owned.sol':positive.sha(SOURCES[mode])}, 'input_kind':'external-report'}
