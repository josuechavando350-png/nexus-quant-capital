"""Reconcile Metric's published audit documents at a single immutable revision."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import unquote

from superhunter.product_source_overlap import inventory
from superhunter.repository_boundary import git_object

DOCS = "83c65a539c91f38f08126856eac62055220cc196"
TREE = "0cbf9f21859732b3d3e2142677bcb8e3df4c3a8e"
SEVERITY = {"H": "High", "M": "Medium", "L": "Low/Info", "I": "Low/Info"}
OUTCOMES = {
    "fix_wording": r"(?:fix confirmed\b|the protocol team fixed this issue in the following PRs/commits:|fixed in PR\s*#)",
    "acknowledged_no_fix_at_report_time": r"This issue has been acknowledged by the team but won['’]t be fixed at this time",
    "documentation_acknowledgment": r"Acknowledged only via documentation\.",
}


def checked_files(source):
    def git(*args):
        return subprocess.check_output(["git", "-C", source, *args])

    raw_commit = git("cat-file", "commit", DOCS)
    if git_object("commit", raw_commit) != DOCS or raw_commit.splitlines()[0] != f"tree {TREE}".encode():
        raise ValueError("Document archive identity mismatch")
    listing = git("ls-tree", "-rtz", TREE)
    count, known = inventory(listing, TREE)
    files = {}
    for rec in git("ls-tree", "-rz", TREE).split(b"\0"):
        if rec:
            meta, name = rec.split(b"\t", 1)
            mode, kind, object_id = meta.split()
            if (mode, kind) != (b"100644", b"blob") or bytes.fromhex(object_id.decode()) not in known:
                raise ValueError("Unexpected entry in the document archive")
            data = git("cat-file", "blob", object_id.decode())
            if git_object("blob", data) != object_id.decode():
                raise ValueError("Document content mismatch")
            files[name.decode()] = data
    if len(files) != count:
        raise ValueError("Incomplete document inventory")
    return files


def summary_table(text, title):
    after = text.split("\n" + title + "\n", 1)[1]
    lines = iter(line.strip() for line in after.splitlines() if line.strip())
    header, values = next(lines).split(), next(lines).split()
    return dict(zip(header, map(int, values), strict=True))


def sherlock(text):
    # Split only at the per-issue headings. A phrase elsewhere in the report cannot resolve an issue.
    found = summary_table(text, "Issues Found")
    pending = summary_table(text, "Issues Not Fixed and Not Acknowledged")
    ids = list(re.finditer(r"(?m)^Issue\s+([HMLI])-(\d+):", text))
    if len({m.groups() for m in ids}) != len(ids):
        raise ValueError("Duplicate Sherlock issue identifier within one report")
    severities = Counter(SEVERITY[m[1]] for m in ids)
    if Counter(found) != severities or not ids or set(pending) != set(found):
        raise ValueError("Sherlock summary and detailed headings disagree")
    outcomes = Counter()
    for i, heading in enumerate(ids):
        end = ids[i + 1].start() if i + 1 < len(ids) else len(text)
        section = text[heading.end():end]
        matched = [label for label, pattern in OUTCOMES.items() if re.search(r"^\s*" + pattern, section, re.I | re.M)]
        if len(matched) > 1:
            raise ValueError("Conflicting disposition wording within one issue")
        outcomes[matched[0] if matched else "unclassified_wording"] += 1
    return {"entries": len(ids), "summary_by_severity": found,
            "not_fixed_and_not_acknowledged": pending, "disposition_wording": dict(outcomes)}


def zellic(text, cover, index_date):
    date_line = re.search(r"(?m)^\s*([A-Z][a-z]+ \d{1,2}, \d{4})\s*$", cover)
    date = datetime.strptime(date_line[1], "%B %d, %Y").date().isoformat()
    if date != index_date:
        raise ValueError("Zellic cover and repository index disagree")
    after = text.split("Breakdown of Finding Impacts\n", 1)[1]
    rows = re.findall(r"(?m)^[^\w\n]*(Critical|High|Medium|Low|Informational)\s+(\d+)[ \t]*$", after[:1800])
    if [name for name, n in rows] != ["Critical", "High", "Medium", "Low", "Informational"]:
        raise ValueError("Incomplete Zellic impact table")
    counts = {name: int(n) for name, n in rows}
    return {"entries": sum(counts.values()), "summary_by_severity": counts, "cover_date": date}


def reconcile(source):
    files = checked_files(source)
    index = files.pop("README.md").decode()
    dates = {unquote(link): date for date, link in re.findall(
        r"(?m)^\| (\d{4}-\d{2}-\d{2}) \| \[.*?\]\(([^)]+\.pdf)\)", index)}
    linked = {unquote(link) for link in re.findall(r"\]\(([^)]+\.pdf)\)", index)}
    if set(files) != linked or len(dates) != 5:
        raise ValueError("Audit index and document inventory disagree")
    reports = []
    dispositions = Counter()
    for name, data in sorted(files.items()):
        extracted = subprocess.check_output(["pdftotext", "-q", "-enc", "UTF-8", "-layout", "-", "-"], input=data).decode("utf-8")
        pages = extracted.rstrip("\n").split("\f")
        if pages[-1] != "":
            raise ValueError("Incomplete PDF page sequence")
        n = len(pages) - 1
        meta = subprocess.check_output(["pdfinfo", "-"], input=data).decode("utf-8")
        if int(re.search(r"(?m)^Pages:\s*(\d+)\s*$", meta)[1]) != n:
            raise ValueError("PDF page count mismatch")
        row = {"file": name, "sha256": hashlib.sha256(data).hexdigest(), "pages": n}
        if name in dates:
            text = unicodedata.normalize("NFKC", "\n".join(pages))
            row["index_date"] = dates[name]
            if name.startswith("sherlock/"):
                row.update(sherlock(text))
                dispositions.update(row["disposition_wording"])
            elif name.startswith("zellic/"):
                row.update(zellic(text, pages[0], dates[name]))
            else:
                raise ValueError("Unexpected report series")
        reports.append(row)
    return {"archive": "https://github.com/Metricxyz/Known_issues", "commit": DOCS, "tree": TREE,
            "files_verified_including_index": len(reports) + 1, "documents": reports,
            "pages_including_appendix": sum(r["pages"] for r in reports),
            "report_entries_before_cross_report_deduplication": sum(r.get("entries", 0) for r in reports),
            "sherlock_disposition_wording": dict(dispositions)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.source), indent=2, ensure_ascii=False, sort_keys=True))
