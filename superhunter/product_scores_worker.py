"""Offline native scoring of fixed local predictions. Imports only the selected wheel environment."""
import asyncio
import json
from pathlib import Path
import resource
import sys


def dspy_score(rows):
    import dspy

    class SavedPrediction(dspy.Module):
        def forward(self, observed):
            return dspy.Prediction(label=observed)

    dataset = [dspy.Example(case_id=key, observed=row['observed'], expected=row['expected']).with_inputs('observed')
               for key, row in rows.items()]
    evaluator = dspy.Evaluate(devset=dataset, metric=lambda example, prediction: example.expected == prediction.label,
                              num_threads=1, max_errors=1, display_progress=False, display_table=False)
    result = evaluator(SavedPrediction())
    return {'by_id': {example.case_id: bool(correct) for example, _, correct in result.results},
            'percentage': result.score}


async def inspect_score(rows):
    from inspect_ai.model import ModelName, ModelOutput
    from inspect_ai.scorer import SampleScore, Target, accuracy, exact
    from inspect_ai.solver import TaskState

    scorer = exact()
    scores = []
    for key, row in rows.items():
        output = ModelOutput.from_content('nqc/saved-predictions', row['observed'])
        state = TaskState(model=ModelName('nqc/saved-predictions'), sample_id=key, epoch=1, input=key,
                          messages=[], completed=True, output=output)
        score = await scorer(state, Target(row['expected']))
        scores.append(SampleScore(score=score, sample_id=key))
    return {'by_id': {s.sample_id: s.score.value == 'C' for s in scores},
            'percentage': 100 * accuracy()(scores)}


if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_CPU, (45, 48))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    sys.path.insert(0, str(Path('lib').resolve()))
    cases = json.loads(sys.stdin.buffer.read(100_001))
    if sys.argv[1] == 'dspy':
        result = {name: dspy_score(rows) for name, rows in cases.items()}
    elif sys.argv[1] == 'inspect':
        result = {name: asyncio.run(inspect_score(rows)) for name, rows in cases.items()}
    else:
        raise ValueError('unknown scorer')
    Path('scores.json').write_text(json.dumps(result, sort_keys=True))
