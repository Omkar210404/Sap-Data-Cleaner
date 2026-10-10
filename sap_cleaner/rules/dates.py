"""Date standardisation: many input formats in, one output format out."""

from __future__ import annotations

from datetime import datetime

from ..runlog import apply_changes


def parse_date(value, formats):
    """Return the date for the first format that fits, or None.

    Formats without separators (such as %Y%m%d) must match exactly, otherwise
    strptime would happily read "2024315" as 2024-03-15.
    """
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        has_separators = not fmt.replace("%", "").isalnum()
        if has_separators or parsed.strftime(fmt) == value:
            return parsed.date()
    return None


def standardise_dates(df, cfg, log):
    """Rewrite dates in the output format; reject values that are not real dates.

    Blank dates are left blank. Whether a blank is acceptable is the mandatory
    rule's decision, not this one's.
    """
    blank_values = set(cfg.get("blank_values", []))
    for column in cfg["columns"]:
        new_values = []
        for row, value in df[column].items():
            if value == "" or value in blank_values:
                new_values.append("")
                continue
            parsed = parse_date(value, cfg["input_formats"])
            if parsed is None:
                log.reject(row, f"invalid date in {column}", f"{column} '{value}' is not a valid date")
                new_values.append(value)
            else:
                new_values.append(parsed.strftime(cfg["output_format"]))
        apply_changes(df, column, new_values, "dates", log)
