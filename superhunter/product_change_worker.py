"""Compare a fixed digest repair entirely in memory using three pinned upstream modules."""
import hashlib
import json
from pathlib import Path
import sys

# The parent reconstructs these modules and wheels from authenticated source bytes.
sys.path[:0] = [str(Path.cwd()), str(Path('lib').resolve())]

import change_core
from aider.diffs import diff_partial_update
from trace_merge import recursive_merge


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def main():
    body = json.load(sys.stdin)
    before, expected = body['before'], body['expected']
    file = 'header.go'
    change = ('*** Begin Patch\n*** Update File: header.go\n@@\n-\t"crypto/md5"\n'
              '+\t"crypto/sha256"\n@@\n-\tdigest := md5.Sum(encoded)\n'
              '+\tdigest := sha256.Sum256(encoded)\n*** End Patch')
    inputs = {file: before}
    patch, fuzz = change_core.text_to_patch(change, inputs)
    action = change_core.patch_to_commit(patch, inputs).changes[file]
    if action.type.value != 'update' or action.old_content != before or fuzz:
        raise ValueError('patch has the wrong source or context')
    after = action.new_content
    try:
        change_core.text_to_patch(change, {file: expected})
    except change_core.DiffError:
        rejected_reapply = True
    else:
        raise ValueError('already corrected input accepted the same change')
    diff = diff_partial_update(before.splitlines(True), after.splitlines(True), final=True, fname=file)
    clean = diff_partial_update(after.splitlines(True), expected.splitlines(True), final=True, fname=file)
    report = recursive_merge({'file': file, 'source': {'before': digest(before)}},
                             {'source': {'after': digest(after)}, 'change': {'unified': diff}},
                             {'change': {'clean_comparison': clean, 'stale_patch_rejected': rejected_reapply},
                              'observation': body['diagnostic']})
    print(json.dumps(report))


if __name__ == '__main__':
    main()
