#!/usr/bin/env python3
"""Read exact original public Git objects/metadata into a separate local store.

This is acquisition, not disconnected replay or certification. No credential,
caller-selected URL/ref/digest, moving branch, workflow mutation or fallback.
"""
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import tempfile
import urllib.request

spec = importlib.util.spec_from_file_location("historical_authority", Path(__file__).with_name("materialize_historical_source.py"))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
GIT_URL = "https://github.com/" + a.SOURCE_REPOSITORY + ".git"
API_URL = "https://api.github.com/repos/" + a.SOURCE_REPOSITORY


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise a.AdapterError("historical metadata redirect rejected")


def read_metadata(url):
    permitted = {API_URL} | {API_URL + "/git/commits/" + oid for oid in a.HISTORICAL_REFS.values()}
    a.require(url in permitted, "unapproved historical metadata endpoint")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                 "User-Agent": "nqc-read-only-historical-acquisition"})
    with opener.open(request, timeout=45) as response:
        a.require(response.status == 200 and response.geturl() == url, "historical metadata endpoint changed")
        raw = response.read(2 * 1024 * 1024 + 1)
    a.require(len(raw) <= 2 * 1024 * 1024, "historical metadata size limit")
    def pairs(items):
        result = {}
        for key, value in items:
            a.require(key not in result, "duplicate historical metadata key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def acquire(output):
    output = Path(output).absolute()
    a.require(output.parent.is_dir() and output.parent.resolve() == output.parent, "acquisition output parent aliases")
    a.require(not output.exists() and not output.is_symlink(), "acquisition output already exists")
    with tempfile.TemporaryDirectory(prefix="nqc-public-source-acquire-", dir=output.parent) as tmp:
        work = Path(tmp)
        env = a.environment(work)
        stage = work / "result"; stage.mkdir()
        store = stage / "source-object-store"; store.mkdir()
        # Repository identity is read before opening Git transport.
        repository = read_metadata(API_URL)
        a.require(repository.get("full_name") == a.SOURCE_REPOSITORY and
                  type(repository.get("id")) is int and repository["id"] == a.SOURCE_REPOSITORY_ID and
                  repository.get("private") is False and repository.get("url") == API_URL,
                  "original public repository identity changed")
        commits = {}
        for ref, oid in a.HISTORICAL_REFS.items():
            record = read_metadata(API_URL + "/git/commits/" + oid)
            commits[ref] = {"sha": record.get("sha"), "tree": {"sha": record.get("tree", {}).get("sha")},
                            "url": record.get("url")}
        repository = {key: repository[key] for key in ("id", "full_name", "private", "url")}
        metadata = {"schema": "nqc-public-historical-source-metadata-v1",
                    "source_repository": a.SOURCE_REPOSITORY, "source_repository_id": a.SOURCE_REPOSITORY_ID,
                    "git_transport_url": GIT_URL,
                    "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "repository_metadata": repository, "commit_metadata": commits}
        metadata_path = stage / "source-metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        a.load_source_metadata(metadata_path)
        a.git(store, "init", "--quiet", "--template=", env=env)
        acquisition_env = dict(env, GIT_ALLOW_PROTOCOL="https")
        refspecs = [oid + ":" + ref for ref, oid in a.HISTORICAL_REFS.items()]
        a.run(["git", "--no-replace-objects", "-c", "protocol.allow=never",
               "-c", "protocol.https.allow=always", "-c", "credential.helper=",
               "-c", "credential.interactive=false", "-c", "http.followRedirects=false",
               "-c", "http.extraHeader=", "-c", "core.hooksPath=/dev/null",
               "-C", store, "fetch", "--no-tags", "--no-write-fetch-head",
               "--no-recurse-submodules", "--", GIT_URL, *refspecs], cwd=store, env=acquisition_env)
        a.verify_source_store(store, env)
        # Retain precisely the original refs; HEAD is deliberately left unborn.
        (stage / "ACQUISITION.json").write_text(json.dumps({
            "schema": "nqc-public-source-acquisition-v1", "source_repository": a.SOURCE_REPOSITORY,
            "repository_id": a.SOURCE_REPOSITORY_ID, "refs": a.HISTORICAL_REFS,
            "trees": a.HISTORICAL_TREES, "metadata_sha256": a.digest(metadata_path.read_bytes()),
            "origin_basis": "DIRECT_FIXED_OFFICIAL_HTTPS_ENDPOINTS_TLS_VERIFIED_NO_ACCOUNT_TOKEN",
            "git_fetch_url": GIT_URL, "object_graph_fsck": "PASS",
            "network_used_for_acquisition": True, "source_checkout_created": False,
            "canonical_recertification": False, "production_authority": False
        }, indent=2, sort_keys=True) + "\n")
        a.publish_no_replace(stage, output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = acquire(args.output)
    except (a.AdapterError, OSError, ValueError, KeyError) as error:
        print("HISTORICAL_ACQUISITION_FAILED: " + str(error), file=sys.stderr)
        return 1
    print("HISTORICAL_PUBLIC_SOURCE_ACQUIRED " + str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
