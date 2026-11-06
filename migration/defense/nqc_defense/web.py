"""M33: WSGI admission endpoint and per-response CSP. Does not open a socket."""

import base64
import secrets

from .codec import Rejected, canonical, response


def security_headers():
    nonce = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    policy = ("default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
              "form-action 'none'; object-src 'none'; script-src 'nonce-" + nonce + "'")
    return [("Content-Security-Policy", policy), ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer")]


class Application:
    def __init__(self, engine):
        self.engine = engine

    def __call__(self, environ, start_response):
        status, output = "200 OK", None
        try:
            if environ.get("PATH_INFO") != "/v1/inspect" or environ.get("QUERY_STRING", ""):
                status, output = "404 Not Found", canonical({"error": "route"})
            elif environ.get("REQUEST_METHOD") != "POST":
                status, output = "405 Method Not Allowed", canonical({"error": "method"})
            elif environ.get("CONTENT_TYPE") != "application/json":
                status, output = "415 Unsupported Media Type", canonical({"error": "content_type"})
            else:
                # The hosting WSGI server must enforce transport framing/timeouts.
                length = environ.get("CONTENT_LENGTH", "")
                if not isinstance(length, str) or not length.isascii() or not length.isdigit() or len(length) > 6:
                    raise Rejected("content_length")
                length = int(length)
                if not 1 <= length <= 65536:
                    status, output = "413 Payload Too Large", canonical({"error": "body_size"})
                else:
                    auth = environ.get("HTTP_AUTHORIZATION", "")
                    if not isinstance(auth, str) or not auth.startswith("Bearer ") or len(auth) != 71:
                        raise Rejected("invalid_token")
                    raw = environ["wsgi.input"].read(length)
                    if len(raw) != length:
                        raise Rejected("body_truncated")
                    result = self.engine.process(raw, auth[7:])
                    status = {"admit": "200 OK", "quarantined": "423 Locked", "denied": "429 Too Many Requests"}[result["decision"]]
                    if result["reasons"] == ["duplicate_request"]:
                        status = "409 Conflict"
                    if "quarantine_budget_exhausted" in result["reasons"]:
                        status = "409 Conflict"
                    if result["reasons"] in (["clock_regressed"], ["evidence_expired"]):
                        status = "503 Service Unavailable"
                    output = response(result)
        except Rejected as exc:
            if str(exc) == "invalid_token":
                status = "401 Unauthorized"
            elif str(exc).startswith("witness_") or str(exc) in {
                    "clock_regressed", "clock_state_invalid", "config_integrity", "config_store_corruption",
                    "policy_changed", "audit_integrity", "audit_sequence", "file_unavailable", "audit_anchor_unavailable"}:
                status = "503 Service Unavailable"
            else:
                status = "400 Bad Request"
            output = canonical({"error": "request_rejected"})
        except Exception:
            # Fail closed; no stack trace, input or secret becomes an HTTP response.
            status, output = "503 Service Unavailable", canonical({"error": "unavailable"})
        headers = [("Content-Type", "application/json"), ("Content-Length", str(len(output))), *security_headers()]
        if status.startswith("405"):
            headers.append(("Allow", "POST"))
        start_response(status, headers)
        return [output]
