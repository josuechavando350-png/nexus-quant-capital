"""Bounded demonstrations of R3 limitations. Never leaves a hung child behind."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
R3 = ROOT.parent / "r3-state-evidence"
sys.path[:0] = [str(R3 / "src"), str(R3 / "scripts")]
from fixtures import encode, make_case
from gateway import Gateway, MathWorker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    packet, policy, _ = make_case(666301)
    now = policy.anchor.timestamp
    a, b = Gateway(policy), Gateway(policy)
    ta = a.ingest(encode(packet), now)
    tb = b.ingest(encode(packet), now)
    accepted = b.facts(ta, now)
    assert ta == tb and ta is not tb and accepted.anchor == policy.anchor
    # An isolated fake worker reads the request and remains silent. The parent
    # explicitly kills it after a 250ms observation window; R3 supplies no timeout.
    fake = args.out / "silent-worker.py"
    fake.write_text("#!" + sys.executable + "\nimport sys,time\nsys.stdin.readline()\ntime.sleep(30)\n")
    fake.chmod(0o755)
    driver = args.out / "driver.py"
    driver.write_text("import sys\nsys.path.insert(0," + repr(str(R3 / "src")) + ")\n"
                      "from gateway import MathWorker\nw=MathWorker(sys.argv[1])\n"
                      "print(w.process.pid,flush=True)\nw.health([99,99000000,1,2,10**36,10**18//2])\n")
    proc = subprocess.Popen([sys.executable, str(driver), str(fake)], stdout=subprocess.PIPE, text=True)
    child_pid = int(proc.stdout.readline())
    hung = False
    try:
        proc.wait(timeout=.25)
    except subprocess.TimeoutExpired:
        hung = True
    finally:
        os.kill(child_pid, 9)
        proc.kill()
        proc.wait(timeout=5)
        proc.stdout.close()
    assert hung
    result = {"r3_cross_instance_ticket_accepted": True,
              "r3_silent_worker_wait_exceeded_250ms": True,
              "child_and_driver_stopped": True,
              "scope": "LOCAL_RESEARCH_LIMITATIONS_NOT_COMMERCIAL_AUTHORIZATION_BYPASS",
              "r3_gateway_sha256": hashlib.sha256((R3 / "src/gateway.py").read_bytes()).hexdigest()}
    (args.out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
