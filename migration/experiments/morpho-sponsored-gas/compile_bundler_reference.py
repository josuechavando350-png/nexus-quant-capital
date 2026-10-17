"""Compile pinned Bundler3/EthereumGeneralAdapter1 import closure; no deployment."""
import argparse
import hashlib
import json
import posixpath
import re
import subprocess
from pathlib import Path

COMMIT="b4014349e3527f44ceaab697b26e29f2b11457f3"
SOLC_SHA256="9a0fb7e0db2c0641dbae1c5cc645dc686820c83af516226abb1c0a2f76636f25"


def compile_reference(source: Path, compiler: Path):
    if hashlib.sha256(compiler.read_bytes()).hexdigest()!=SOLC_SHA256:
        raise ValueError("unverified solc 0.8.28 Linux binary")
    def git(repo,*argv):
        return subprocess.check_output(["git","-C",str(repo),*argv])
    def blob(repo,rev,path):
        entries=git(repo,"ls-tree","-r",rev).decode().splitlines()
        for line in entries:
            meta,name=line.split("\t");mode,kind,sha=meta.split()
            if kind=="commit" and path.startswith(name+"/"):
                return blob(repo/name,sha,path[len(name)+1:])
            if name==path:
                if kind!="blob" or mode!="100644":raise ValueError("unsupported reference mode")
                return git(repo,"cat-file","blob",sha),sha,rev
        raise ValueError(f"missing pinned reference: {path}")
    targets={"src/Bundler3.sol":"Bundler3","src/adapters/EthereumGeneralAdapter1.sol":"EthereumGeneralAdapter1"}
    pending=list(targets);sources={};manifest=[]
    while pending:
        name=pending.pop()
        if name in sources:continue
        data,sha,revision=blob(source,COMMIT,name)
        if hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()!=sha:
            raise ValueError("reference blob changed")
        content=data.decode();sources[name]={"content":content}
        manifest.append({"path":name,"git_blob":sha,"source_commit":revision,"sha256":hashlib.sha256(data).hexdigest()})
        for imp in re.findall(r'import\s+(?:[^;]*?\s+from\s+)?["\']([^"\']+)["\']\s*;',content):
            if imp.startswith("."):
                resolved=posixpath.normpath(posixpath.join(posixpath.dirname(name),imp))
            elif imp.startswith("solmate/"):
                resolved="lib/permit2/lib/solmate/"+imp[len("solmate/"):]
            else:raise ValueError(f"unhandled import {imp}")
            if resolved.startswith("../"):raise ValueError("reference escapes source root")
            pending.append(resolved)
    std={"language":"Solidity","sources":sources,"settings":{
        "optimizer":{"enabled":True,"runs":999999},"viaIR":True,"evmVersion":"cancun",
        "metadata":{"bytecodeHash":"none"},"remappings":["solmate/=lib/permit2/lib/solmate/"],
        "outputSelection":{p:{n:["abi","evm.bytecode.object","evm.deployedBytecode.object"]} for p,n in targets.items()}}}
    result=subprocess.run([str(compiler),"--standard-json"],input=json.dumps(std),text=True,capture_output=True,check=True)
    output=json.loads(result.stdout)
    errors=[e for e in output.get("errors",[]) if e["severity"]=="error"]
    if errors:raise ValueError(errors)
    folder=Path(__file__).parent/"out-upstream";folder.mkdir(exist_ok=True)
    for path,name in targets.items():
        c=output["contracts"][path][name]
        artifact={"abi":c["abi"],"bytecode":{"object":"0x"+c["evm"]["bytecode"]["object"]},
                  "deployedBytecode":{"object":"0x"+c["evm"]["deployedBytecode"]["object"]}}
        (folder/f"{name}.json").write_text(json.dumps(artifact,indent=2)+"\n")
    (folder/"bundler-manifest.json").write_text(json.dumps({"commit":COMMIT,"solc_sha256":SOLC_SHA256,
        "sources":sorted(manifest,key=lambda x:x["path"]),"scope":"LOCAL_REFERENCE_NOT_HISTORICAL_RUNTIME_PROOF"},indent=2)+"\n")
    print(json.dumps({"source_commit":COMMIT,"source_files":len(sources),"contracts":list(targets.values())}))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",required=True,type=Path);p.add_argument("--solc",required=True,type=Path)
    a=p.parse_args();compile_reference(a.source.resolve(),a.solc.resolve())
