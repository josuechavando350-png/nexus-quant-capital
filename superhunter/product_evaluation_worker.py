"""Execute only three pinned, offline representation scoring modules in the temporary work tree."""
import importlib.util
import json
from pathlib import Path
import sys


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(name + '.py').resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    sys.path.insert(0, str(Path('lib').resolve()))
    gaia = load('gaia_scorer').question_scorer
    whisper = load('english_normalizer').BasicTextNormalizer()
    fbeta = load('ragas_utils').fbeta_score
    source = json.load(sys.stdin)
    results = {}
    for mode, rows in source.items():
        gaia_flags, whisper_flags = [], []
        counts = {name: [0, 0, 0] for name in ('extraData', 'gasUsed', 'hash', 'logsBloom', 'miner')}
        for row in rows:
            truth, answer = row['truth'], row['answer']
            gaia_flags.append(gaia(answer, truth))
            whisper_flags.append(whisper(answer) == whisper(truth))
            for field, tally in counts.items():
                predicted, reference = field == answer, field == truth
                tally[0] += predicted and reference
                tally[1] += predicted and not reference
                tally[2] += not predicted and reference
        grades = {name: {str(beta): fbeta(*counts[name], beta=beta) for beta in (.5, 1., 2.)} for name in counts}
        results[mode] = {'gaia': gaia_flags, 'whisper': whisper_flags, 'ragas': grades}
    json.dump(results, sys.stdout, allow_nan=False)


if __name__ == '__main__':
    main()
