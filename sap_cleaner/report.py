"""Plain-text summary of a run. Every number is counted from the run's own tables."""

from __future__ import annotations

from collections import Counter

from .pipeline import SOURCE_ROW


def summarise(result):
    """Return the counts the report prints."""
    changes = result.changes
    by_rule = Counter(changes["RULE"])
    fills = Counter(changes.loc[changes["RULE"] == "mandatory", "COLUMN"])
    reasons = Counter(category for row in result.rejected[SOURCE_ROW]
                      for category in dict.fromkeys(result.log.categories(row)))
    return {
        "rows_read": result.rows_read,
        "rows_cleaned": len(result.cleaned),
        "rows_rejected": len(result.rejected),
        "rows_flagged": sum(1 for row in result.log.flags if not result.log.is_rejected(row)),
        "changes_total": len(changes),
        "changes_by_rule": {rule: by_rule[rule] for rule in result.rules_run if by_rule[rule]},
        "fills_by_field": dict(sorted(fills.items())),
        "rejects_by_reason": dict(sorted(reasons.items(), key=lambda item: (-item[1], item[0]))),
    }


def _table(counts, empty):
    if not counts:
        return [f"  {empty}"]
    width = max(len(str(label)) for label in counts)
    return [f"  {str(label).ljust(width)}  {count:>5}" for label, count in counts.items()]


def build_report(result, input_name, data_type, rules_source):
    summary = summarise(result)
    lines = [
        "SAP DATA CLEANER - SUMMARY REPORT",
        "=================================",
        f"Input file : {input_name}",
        f"Data type  : {data_type}",
        f"Rules file : {rules_source}",
        f"Rules run  : {', '.join(result.rules_run) or 'none'}",
        "",
        "ROWS",
        *_table({"Read": summary["rows_read"], "Cleaned": summary["rows_cleaned"],
                 "Rejected": summary["rows_rejected"]}, ""),
    ]
    if summary["rows_flagged"]:
        lines.append(f"  {summary['rows_flagged']} cleaned rows are flagged as possible near-duplicates.")
    lines += [
        "",
        "CHANGES MADE TO CLEANED ROWS, BY RULE",
        *_table({**summary["changes_by_rule"], "Total": summary["changes_total"]}, ""),
        "  Rejected rows are written back unchanged, so changes to them are not counted.",
        "",
        "BLANK VALUES FILLED WITH A DEFAULT, BY FIELD",
        *_table(summary["fills_by_field"], "none"),
        "",
        "REJECTED ROWS, BY REASON",
        *_table(summary["rejects_by_reason"], "none"),
    ]
    if summary["rows_rejected"]:
        lines.append("  A row with several problems is counted once under each reason.")

    lines += ["", "EXAMPLES OF CHANGES (first one per rule)"]
    examples = result.changes.drop_duplicates("RULE")
    if examples.empty:
        lines.append("  none")
    for change in examples.itertuples(index=False):
        lines.append(f"  row {change.SOURCE_ROW:<4} {change.COLUMN:<6} "
                     f"{change.OLD_VALUE!r} -> {change.NEW_VALUE!r}  ({change.RULE})")
    return "\n".join(lines) + "\n"
