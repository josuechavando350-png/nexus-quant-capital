#!/usr/bin/env python3
"""Read only fixed public GitHub seed metadata; never download or replace the seed.

TLS authenticates the fixed API endpoint, not a GitHub account. No token,
credential, proxy, redirect, alternate host, moving ref or caller URL is accepted.
The unchanged historical verifier must separately authenticate these snapshots
and the audited local archive at its actual verification time.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import ssl
import urllib.request

API = "https://api.github.com/repos/josuechavando350-png/nexus-engine"
ENDPOINTS = {
    "repository": API,
    "run": API + "/actions/runs/36820687233",
    "artifact": API + "/actions/artifacts/11143129177",
    "commit": API + "/git/commits/a33a012591cd6625ddb921d995bb1bd95b4a5406",
}
LIMIT = 2 * 1024 * 1024
FIELDS = {
    "repository": ("id", "full_name", "private", "url"),
    "run": ("id", "run_attempt", "name", "path", "workflow_id", "head_sha", "head_branch",
            "event", "status", "conclusion", "url", "html_url", "workflow_url"),
    "artifact": ("id", "name", "size_in_bytes", "created_at", "expires_at", "digest", "expired",
                 "url", "archive_download_url"),
    "commit": ("sha", "url"),
}
NESTED_FIELDS = {
    "repository": {},
    "run": {"repository": ("id", "full_name"), "head_repository": ("id", "full_name"),
            "head_commit": ("id", "tree_id")},
    "artifact": {"workflow_run": ("id", "repository_id", "head_repository_id", "head_sha", "head_branch")},
    "commit": {"tree": ("sha", "url")},
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise ValueError("metadata redirect is forbidden")


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate metadata key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("non-finite metadata number")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    if type(value) is not dict:
        raise ValueError("metadata must be an object")
    return value


def read_endpoint(opener, url):
    if url not in ENDPOINTS.values():
        raise ValueError("unreviewed metadata endpoint")
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nqc-standalone-d06-readonly-metadata/1",
    })
    with opener.open(request, timeout=30) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("metadata status or origin changed")
        raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("oversized metadata response")
        strict_json(raw)
        headers = {name: response.headers.get(name) for name in
                   ("Date", "ETag", "X-GitHub-Request-Id")}
    return raw, headers


def project_metadata(label, payload):
    """Drop unrelated homepage/client/actor data without rewriting consumed fields."""
    projected = {key: payload[key] for key in FIELDS[label]}
    for key, fields in NESTED_FIELDS[label].items():
        if type(payload[key]) is not dict:
            raise ValueError("invalid nested metadata object")
        projected[key] = {field: payload[key][field] for field in fields}
    return projected


def collect(output):
    output = Path(output).absolute()
    if output.resolve() != output or not output.parent.is_dir():
        raise ValueError("metadata output path aliases or missing parent")
    output.mkdir(mode=0o700, exist_ok=False)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    started = datetime.now(timezone.utc)
    rows = []
    for label, endpoint in ENDPOINTS.items():
        raw, headers = read_endpoint(opener, endpoint)
        payload = strict_json(raw)
        if label == "repository" and not (
                type(payload.get("id")) is int and payload["id"] == 1333360261 and
                payload.get("full_name") == "josuechavando350-png/nexus-engine" and
                payload.get("private") is False):
            raise ValueError("original repository identity or public visibility changed")
        projected = (json.dumps(project_metadata(label, payload), indent=2, sort_keys=True,
                                allow_nan=False) + "\n").encode()
        (output / (label + ".json")).write_bytes(projected)
        rows.append({"path": label + ".json", "endpoint": endpoint,
                     "sha256": hashlib.sha256(projected).hexdigest(), "size": len(projected),
                     "source_response_sha256": hashlib.sha256(raw).hexdigest(),
                     "source_response_size": len(raw),
                     "response_headers": headers})
    receipt = {
        "schema": "nqc-original-d06-metadata-acquisition-v1",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "origin_basis": "FIXED_PUBLIC_GITHUB_API_HTTPS_TLS_NO_REDIRECT",
        "projection": "ONLY_REPOSITORY_IDENTITY_AND_UNCHANGED_AUTHENTICATOR_INPUT_FIELDS",
        "raw_responses_retained": False,
        "account_authenticated": False, "token_used": False,
        "original_archive_downloaded": False, "canonical_recertification": False,
        "files": rows,
    }
    (output / "metadata-acquisition.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    collect(args.output)
