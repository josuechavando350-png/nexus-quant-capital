import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def run(args, cwd, **kwargs):
    return subprocess.run(args, cwd=cwd, check=True, **kwargs)


def measure(product, out):
    out.mkdir(parents=True, exist_ok=False)
    work = out / "work"
    work.mkdir()
    shutil.copytree(product / "superhunter", work / "superhunter", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(HERE / "qa_tests", work / "qa_tests")
    shutil.copyfile(HERE / "pyproject.toml", work / "pyproject.toml")
    python = sys.executable
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    run([python, "-m", "coverage", "run", "--branch", "-m", "pytest", "-q", "qa_tests"], work, env=env)
    run([python, "-m", "coverage", "json", "-o", str(out / "coverage.json")], work, env=env)
    coverage = json.loads((out / "coverage.json").read_bytes())["files"]
    summary = {}
    for module, function in [("superhunter/tools/verify_review_115.py", "check_preserved_operations"),
                             ("superhunter/product_dependency_attributions.py", "parse_mod")]:
        fn = coverage[module]["functions"][function]
        summary[function] = fn["summary"]
        if not fn["summary"]["num_branches"] or fn["missing_branches"]:
            raise ValueError(f"unvisited branches in {function}: {fn['missing_branches']}")
    mutmut = str(Path(python).with_name("mutmut"))
    # Copy the exact production function to avoid generating thousands of untested
    # variants for unrelated functions in the same module.
    source = (work / "superhunter/tools/verify_review_115.py").read_text()
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
              and n.name == "check_preserved_operations")
    body = ast.get_source_segment(source, fn)
    (work / "mutation_subject.py").write_text(
        "from superhunter.tools.verify_review_115 import EvidenceError, canonical, sha\n\n" + body + "\n")
    target = "mutation_subject.x_check_preserved_operations__mutmut_*"
    env["NQC_MUTATION"] = "1"
    with (out / "mutation.log").open("w") as log:
        run([mutmut, "run", "--max-children", "2", target], work, env=env, stdout=log, stderr=subprocess.STDOUT)
    meta = work / "mutants/mutation_subject.py.meta"
    mutants = json.loads(meta.read_bytes())["exit_code_by_key"]
    # Mutmut 3.8.1 records pytest's exit status (1 is a killed mutant, 0 survives).
    scores = {k:v for k,v in mutants.items() if k.startswith(target[:-1])}
    if not scores or any(type(v) is not int or v not in (0, 1) for v in scores.values()):
        raise ValueError(f"incomplete or invalid mutation results: {scores}")
    result = {"functions": summary, "mutants": scores,
              "killed": sum(v == 1 for v in scores.values()), "survived": sum(v == 0 for v in scores.values())}
    (out / "tool-score.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k != "mutants"}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("product", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args()
    measure(args.product.resolve(), args.out.resolve())
