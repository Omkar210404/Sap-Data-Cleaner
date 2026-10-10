"""Validation against the built-in reference lists (units of measure, countries)."""

from __future__ import annotations

from ..runlog import apply_changes


def check_reference(df, columns, reference, label, rule, log):
    """Map known aliases to their code, then reject values that are not in the list.

    Blank values are skipped: whether a blank is acceptable is the mandatory
    rule's decision.
    """
    valid, aliases = reference["valid"], reference["aliases"]
    for column in columns:
        new_values = []
        for row, value in df[column].items():
            code = value.upper()
            code = aliases.get(code, code)
            if value == "":
                new_values.append("")
            elif code in valid:
                new_values.append(code)
            else:
                log.reject(row, f"unknown {label} in {column}", f"{column} '{value}' is not a known {label}")
                new_values.append(value)
        apply_changes(df, column, new_values, rule, log)


def unit_of_measure(df, cfg, reference, log):
    check_reference(df, cfg["columns"], reference["units_of_measure"], "unit of measure", "unit_of_measure", log)


def country(df, cfg, reference, log):
    check_reference(df, cfg["columns"], reference["countries"], "country code", "country", log)
