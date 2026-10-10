"""The output files of a run, as text. Shared by the CLI and the web interface
so both produce byte-for-byte the same files."""

from __future__ import annotations

from .report import build_report

TABLES = ("cleaned", "rejected", "changes")


def build_outputs(result, stem, delimiter, input_name, data_type, rules_source):
    """Return {file name: file text} for the three CSVs and the report."""
    files = {f"{stem}_{kind}.csv": getattr(result, kind).to_csv(index=False, sep=delimiter, lineterminator="\n")
             for kind in TABLES}
    files[f"{stem}_report.txt"] = build_report(result, input_name, data_type, rules_source)
    return files
