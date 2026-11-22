"""Fixed on-disk layout of the two-replay product dossiers, independent of producers."""
from pathlib import PurePosixPath

BASE = 'product_supply/consolidated-acceptance'
PROFILE_DIRECTORIES = {
    'core-eight': BASE,
    'accounting': BASE + '-accounting',
    'canonical-header': BASE + '-header',
    'grpc-schema': BASE + '-grpc-schema',
    'html-review': BASE + '-html-review',
    'report-interop': BASE + '-report-interop',
    'evidence-contracts': BASE + '-evidence-contracts',
    'supply-and-reporting': BASE + '-supply-and-reporting',
    'vendored-attributions': BASE + '-vendored-attributions',
    'publication-policy': BASE + '-publication-policy',
}
RUN_DIRECTORIES = ('first', 'second')
RUN_FILES = ('result.json', 'run-inputs.json', 'session.json')
DOSSIER_FILES = ('acceptance.json', *(f'{run}/{name}' for run in RUN_DIRECTORIES for name in RUN_FILES))
PATH_GROUPS = tuple(tuple(f'{directory}/{name}' for name in DOSSIER_FILES)
                    for directory in PROFILE_DIRECTORIES.values())
ALL_FILES = frozenset(path for group in PATH_GROUPS for path in group)


def check_directory(relative, directories, names):
    """An unpublished dossier may be absent. Every observed one must be complete."""
    if relative == 'product_supply':
        if any(str(PurePosixPath(relative) / name) in PROFILE_DIRECTORIES.values() for name in names):
            raise ValueError('acceptance dossier is not a directory')
    elif relative in PROFILE_DIRECTORIES.values():
        if set(directories) != set(RUN_DIRECTORIES) or set(names) != {'acceptance.json'}:
            raise ValueError('unexpected or incomplete acceptance dossier')
    elif str(PurePosixPath(relative).parent) in PROFILE_DIRECTORIES.values():
        if directories or set(names) != set(RUN_FILES):
            raise ValueError('unexpected or incomplete acceptance replay')
