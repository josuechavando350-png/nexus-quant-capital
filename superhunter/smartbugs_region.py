"""The SmartBugs SARIF source-region converter, imported as a bounded library function.

Upstream sb/sarif.py at a246003622775c730d5522429d8fed8846406e17.
The result_region function is verbatim. This module replaces the upstream imports
with the two typing names the function uses. See product_supply/source-excerpts.
"""
from typing import Any, Optional


def result_region(finding: dict[str, Any]) -> Optional[dict[str, int]]:
    region_dict: dict[str, int] = {}

    # source code
    for f, r in (
        ("line", "startLine"),
        ("column", "startColumn"),
        ("line_end", "endLine"),
        ("column_end", "endColumn"),
    ):
        if f in finding:
            region_dict[r] = int(finding[f])

    if region_dict:
        return region_dict

    # hex code
    for addr, line_key, col_key in (
        ("address", "startLine", "startColumn"),
        ("address_end", "endLine", "endColumn"),
    ):
        if addr in finding:
            region_dict[line_key] = 1
            region_dict[col_key] = 1 + 2 * int(finding[addr])

    # fmt: off
    return (
        region_dict if region_dict else
        None
    )
    # fmt: on
