"""Compile pinned original Morpho 0.8.19 into a local test artifact, no deployment.

Reads original Git blobs, never rewrites upstream or the preserved NQC sources.
The resulting bytecode is a LOCAL reference, not certified mainnet runtime.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

COMMIT = "9cf6d5b844625ba108e36d1cf911f5d2faf7c136"
SOLC_SHA256 = "7a5c1d3dc9a8eba62bb2ec37192c9178ae5fe8a54a56e5573fd3c9c17cd9eb48"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--solc", required=True, type=Path)
    args = p.parse_args()
    compiler = args.solc.resolve()
    if hashlib.sha256(compiler.read_bytes()).hexdigest() != SOLC_SHA256:
        raise ValueError("unverified solc 0.8.19 Linux binary")
    def git(*argv):
        return subprocess.check_output(["git", "-C", str(args.source), *argv])
    entries = git("ls-tree", "-r", COMMIT, "src").decode().splitlines()
    sources, manifest = {}, []
    for line in entries:
        meta, name = line.split("\t")
        mode, kind, sha = meta.split()
        if not name.endswith(".sol"):
            continue
        if mode != "100644" or kind != "blob":
            raise ValueError("unsupported source object")
        data = git("cat-file", "blob", sha)
        actual = hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
        if actual != sha:
            raise ValueError("source Git identity mismatch")
        sources[name] = {"content":data.decode()}
        manifest.append({"path":name, "git_blob":sha, "sha256":hashlib.sha256(data).hexdigest()})
    standard = {"language":"Solidity", "sources":sources, "settings":{
        "optimizer":{"enabled":True,"runs":200}, "evmVersion":"paris",
        "outputSelection":{"src/Morpho.sol":{"Morpho":["abi","evm.bytecode.object","evm.deployedBytecode.object"]}}
    }}
    r = subprocess.run([str(compiler), "--standard-json"], input=json.dumps(standard),
                       text=True, capture_output=True, check=True)
    output = json.loads(r.stdout)
    errors = [x for x in output.get("errors",[]) if x["severity"]=="error"]
    if errors:
        raise ValueError(errors)
    c = output["contracts"]["src/Morpho.sol"]["Morpho"]
    folder = Path(__file__).parent / "out-upstream"
    folder.mkdir(exist_ok=True)
    artifact = {"abi":c["abi"], "bytecode":{"object":"0x"+c["evm"]["bytecode"]["object"]},
                "deployedBytecode":{"object":"0x"+c["evm"]["deployedBytecode"]["object"]}}
    (folder/"Morpho.json").write_text(json.dumps(artifact,indent=2)+"\n")
    proof = {"source_commit":COMMIT,"solc_sha256":SOLC_SHA256,"sources":manifest,
             "creation_bytecode_sha256":hashlib.sha256(bytes.fromhex(c["evm"]["bytecode"]["object"])).hexdigest(),
             "scope":"LOCAL_ORIGINAL_SOURCE_BUILD_NOT_DEPLOYED_RUNTIME_CERTIFICATE"}
    (folder/"manifest.json").write_text(json.dumps(proof,indent=2)+"\n")
    print(json.dumps({"source_commit":COMMIT,"sources":len(sources),"artifact":str(folder/"Morpho.json")}))


if __name__ == "__main__":
    main()
