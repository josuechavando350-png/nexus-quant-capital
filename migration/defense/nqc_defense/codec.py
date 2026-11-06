"""Bounded, unambiguous JSON and explicit request/response schemas."""

import json
import re


class Rejected(ValueError):
    """An input or integrity check failed. Messages never include input contents."""


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def decode(data, max_bytes=65536, max_nodes=4096):
    if not isinstance(data, bytes) or len(data) > max_bytes:
        raise Rejected("input_size")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Rejected("duplicate_key")
            result[key] = value
        return result

    def invalid_number(_):
        raise Rejected("non_finite_number")

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=invalid_number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Rejected("invalid_json") from exc
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > 24 or count > max_nodes:
            raise Rejected("json_complexity")
        if isinstance(item, (dict, list)):
            stack.extend((v, depth + 1) for v in (item.values() if isinstance(item, dict) else item))
        elif isinstance(item, float):
            raise Rejected("floating_point_not_allowed")
        elif isinstance(item, int) and item.bit_length() > 64:
            raise Rejected("integer_range")
    return value


def fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise Rejected("schema_fields")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise Rejected("identifier")
    return value


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise Rejected("integer_range")
    return value


def request(data):
    value = decode(data)
    fields(value, ("request_id", "asset"))
    identifier(value["request_id"])
    identifier(value["asset"])
    return value


def response(value):
    """M75's runtime subset: reject extra output fields instead of leaking them."""
    fields(value, ("request_id", "asset", "decision", "reasons", "audit_head", "receipt_sha256"))
    identifier(value["request_id"])
    identifier(value["asset"])
    if value["decision"] not in {"admit", "quarantined", "denied"}:
        raise Rejected("response_decision")
    if type(value["reasons"]) is not list or len(value["reasons"]) > 8:
        raise Rejected("response_reasons")
    for reason in value["reasons"]:
        identifier(reason)
    if not isinstance(value["audit_head"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["audit_head"]):
        raise Rejected("audit_head")
    if not isinstance(value["receipt_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["receipt_sha256"]):
        raise Rejected("receipt_digest")
    return canonical(value)
