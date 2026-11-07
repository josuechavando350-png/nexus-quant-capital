"""Three immutable detector controls; no external or caller-supplied sources."""
from . import slither_owned_runner as positive, slither_control_pair as pair

SOURCES = {'positive':positive.OWNED_SOURCE, 'clean':pair.CLEAN_SOURCE,
           'comparison':pair.COMPARISON_SOURCE}
SCOPES = {'positive':'owned-fixed-local-fixture', 'clean':'owned-fixed-local-fixture-clean',
          'comparison':'owned-fixed-local-fixture-comparison'}
FIXTURE_COMMIT = 'b18b23128a601498a3dba8fc0bfcbbd2eb726934'
WORKER_POLICY = {'wall_seconds':90,'cpu_seconds':35,'address_space_bytes':2*1024**3,
                 'file_bytes':2_000_000,'open_files':96}


def context(mode: str, normalized_sha256: str) -> dict:
    return {'schema_version':1, 'scope_id':SCOPES[mode],
            'repository':{'repo':'superhunter-owned/fixture','commit':FIXTURE_COMMIT},
            'tool':{'name':'slither','version':positive.SCANNER_VERSION},
            'detectors':[positive.DETECTOR], 'report_sha256':normalized_sha256,
            'sources':{'Owned.sol':positive.sha(SOURCES[mode])}, 'input_kind':'external-report'}
