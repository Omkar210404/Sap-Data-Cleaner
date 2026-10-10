"""Format standardisation: whitespace, letter case and ID padding."""

from __future__ import annotations

import re

from ..runlog import apply_changes

_WHITESPACE = re.compile(r"\s+")
_DIGITS = re.compile(r"[0-9]+")
# "100007.0": a numeric ID that a spreadsheet turned into a decimal number.
_FLOAT_ARTEFACT = re.compile(r"[0-9]+\.0+")


def trim(df, cfg, log):
    """Strip and collapse whitespace in every column; turn null tokens into blanks."""
    null_tokens = {token.upper() for token in cfg.get("null_tokens", [])}

    def clean(value):
        text = _WHITESPACE.sub(" ", value).strip()
        return "" if text.upper() in null_tokens else text

    for column in df.columns:
        apply_changes(df, column, df[column].map(clean), "trim", log)


def uppercase(df, cfg, log):
    for column in cfg["columns"]:
        apply_changes(df, column, df[column].map(str.upper), "uppercase", log)


def zero_pad(df, cfg, log):
    """Pad numeric IDs with leading zeros to a fixed width; reject unusable IDs.

    Alphanumeric IDs are uppercased but not padded, which is how SAP stores them.
    """
    pattern = re.compile(cfg["allowed_pattern"]) if cfg.get("allowed_pattern") else None
    for column, width in cfg["columns"].items():
        new_values = []
        for row, value in df[column].items():
            text = value.upper()
            if _FLOAT_ARTEFACT.fullmatch(text):
                text = text.split(".")[0]
            if _DIGITS.fullmatch(text):
                text = text.lstrip("0").zfill(width)
            if not text:
                pass  # blank: left for the mandatory rule
            elif len(text) > width:
                log.reject(row, f"invalid {column}", f"{column} '{value}' is longer than {width} characters")
                text = value
            elif pattern and not pattern.fullmatch(text):
                log.reject(row, f"invalid {column}", f"{column} '{value}' contains characters that are not allowed")
                text = value
            new_values.append(text)
        apply_changes(df, column, new_values, "zero_pad", log)
