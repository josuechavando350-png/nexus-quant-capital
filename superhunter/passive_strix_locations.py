"""Extracted from Strix for local SARIF location validation in NQC. See PASSIVE_SOURCE_BATCH.md."""
from pathlib import PurePosixPath
from typing import Any

def _build_physical_locations(raw_locations: Any) -> tuple[list[dict[str, Any]], int]:
    """Return SARIF physical locations and a count of dropped unsafe locations."""
    if not isinstance(raw_locations, list):
        return [], 0

    locations: list[dict[str, Any]] = []
    dropped_location_count = 0
    for location in raw_locations:
        if not isinstance(location, dict):
            dropped_location_count += 1
            continue

        file_path = _string_value(location.get("file"))
        start_line = location.get("start_line")
        end_line = location.get("end_line")
        if not file_path or type(start_line) is not int or start_line < 1:
            dropped_location_count += 1
            continue
        uri = _sarif_uri(file_path)
        if uri is None:
            dropped_location_count += 1
            continue

        region: dict[str, Any] = {"startLine": start_line}
        if type(end_line) is int and end_line >= start_line:
            region["endLine"] = end_line

        snippet = _string_value(location.get("snippet"))
        if snippet:
            region["snippet"] = {"text": snippet}

        physical_location: dict[str, Any] = {
            "artifactLocation": {"uri": uri},
            "region": region,
        }
        entry: dict[str, Any] = {"physicalLocation": physical_location}

        label = _string_value(location.get("label"))
        if label:
            entry["message"] = {"text": label}

        locations.append(entry)

    return locations, dropped_location_count


def _sarif_uri(file_path: str) -> str | None:
    """Return a safe repo-relative SARIF URI, or None for unsafe paths."""
    uri = PurePosixPath(file_path.replace("\\", "/")).as_posix()
    parts = PurePosixPath(uri).parts
    if not uri or uri.startswith("/") or not parts:
        return None
    if ":" in parts[0] or any(part == ".." for part in parts):
        return None
    return uri


def _string_value(value: Any) -> str | None:
    """Return a stripped non-empty string value, or None."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None
