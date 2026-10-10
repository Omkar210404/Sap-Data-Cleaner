"""Read one export, run the configured rules over it and build the output tables."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import RULE_ORDER
from .rules import dates, duplicates, mandatory, reference, standardise
from .runlog import RunLog

SOURCE_ROW = "SOURCE_ROW"
REJECT_REASONS = "REJECT_REASONS"
NEAR_DUPLICATE_NOTE = "NEAR_DUPLICATE_NOTE"

RULES = {
    "trim": lambda df, cfg, ref, log: standardise.trim(df, cfg, log),
    "uppercase": lambda df, cfg, ref, log: standardise.uppercase(df, cfg, log),
    "zero_pad": lambda df, cfg, ref, log: standardise.zero_pad(df, cfg, log),
    "dates": lambda df, cfg, ref, log: dates.standardise_dates(df, cfg, log),
    "unit_of_measure": reference.unit_of_measure,
    "country": reference.country,
    "mandatory": lambda df, cfg, ref, log: mandatory.mandatory(df, cfg, log),
    "exact_duplicates": lambda df, cfg, ref, log: duplicates.exact_duplicates(df, cfg, log),
    "near_duplicates": lambda df, cfg, ref, log: duplicates.near_duplicates(df, cfg, log),
}


class InputError(Exception):
    """The input file is missing, unreadable or lacks required columns."""


@dataclass
class CleanResult:
    cleaned: pd.DataFrame    # rows that passed, with fixes applied
    rejected: pd.DataFrame   # rows that failed, as they were in the input, plus the reasons
    changes: pd.DataFrame    # one line per change made to a cleaned row
    rows_read: int
    rules_run: list
    log: RunLog


def read_input(source, delimiter=",", encoding="utf-8-sig", name=None):
    """Read a CSV with every value as text, so IDs keep their leading zeros.

    `source` is a path or an open binary file; `name` is what error messages
    call it. The index is the source row number as a spreadsheet shows it: the
    header is row 1 and the first data row is row 2.
    """
    name = name or source
    try:
        df = pd.read_csv(source, sep=delimiter, encoding=encoding, dtype=str,
                         keep_default_na=False, na_filter=False)
    except FileNotFoundError:
        raise InputError(f"input file not found: {name}") from None
    except pd.errors.EmptyDataError:
        raise InputError(f"input file is empty: {name}") from None
    except LookupError:
        raise InputError(f"unknown encoding: {encoding}") from None
    except (pd.errors.ParserError, UnicodeDecodeError) as error:
        raise InputError(f"could not read {name}: {error}") from None
    df = df.fillna("")
    df.columns = [str(column).strip() for column in df.columns]
    df.index = range(2, len(df) + 2)
    return df


def clean(df, config, reference_lists):
    """Apply the enabled rules in RULE_ORDER and split the rows into cleaned and rejected."""
    missing = [column for column in config["columns"] if column not in df.columns]
    if missing:
        raise InputError(f"input file is missing columns the rules need: {', '.join(missing)}")

    work = df.copy()
    log = RunLog()
    rules_run = []
    for name in RULE_ORDER:
        rule = config["rules"].get(name)
        if rule is None or not rule.get("enabled", True):
            continue
        RULES[name](work, rule, reference_lists, log)
        rules_run.append(name)

    rejected_rows = [row for row in df.index if log.is_rejected(row)]
    cleaned = work.drop(index=rejected_rows)
    if "near_duplicates" in rules_run and config["rules"]["near_duplicates"].get("action") == "flag":
        cleaned[NEAR_DUPLICATE_NOTE] = [log.flags.get(row, "") for row in cleaned.index]

    # Rejected rows go back exactly as they came in, so they can be fixed at the source.
    rejected = df.loc[rejected_rows].copy()
    rejected.insert(0, REJECT_REASONS, ["; ".join(log.reasons(row)) for row in rejected_rows])
    rejected.insert(0, SOURCE_ROW, rejected_rows)

    kept = sorted((c for c in log.changes if not log.is_rejected(c["row"])), key=lambda c: c["row"])
    changes = pd.DataFrame(kept, columns=["row", "column", "old", "new", "rule"])
    changes.columns = [SOURCE_ROW, "COLUMN", "OLD_VALUE", "NEW_VALUE", "RULE"]

    return CleanResult(cleaned, rejected, changes, len(df), rules_run, log)
