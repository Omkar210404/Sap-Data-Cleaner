"""Duplicate detection.

Only rows that have not already been rejected take part, so the first
occurrence that is kept is always a usable row. Later occurrences are never
merged into it: they are rejected (or flagged) with a pointer to the row kept.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_NON_WORD = re.compile(r"[\W_]+")
_NUMBERS = re.compile(r"\d+")


def exact_duplicates(df, cfg, log):
    """Reject later rows that repeat the key of an earlier row.

    If every other column matches too it is an exact duplicate; otherwise the
    same key carries conflicting data, which is reported as a key conflict.
    """
    key = cfg["key"]
    fold = str.casefold if cfg.get("ignore_case", True) else str
    columns = list(df.columns)
    key_positions = [columns.index(column) for column in key]
    first_seen = {}
    for row, values in zip(df.index, df.itertuples(index=False, name=None)):
        if log.is_rejected(row):
            continue
        values = tuple(fold(value) for value in values)
        key_value = tuple(values[position] for position in key_positions)
        if key_value not in first_seen:
            first_seen[key_value] = (row, values)
            continue
        first_row, first_values = first_seen[key_value]
        differing = [c for c, kept, this in zip(columns, first_values, values) if kept != this]
        if differing:
            log.reject(row, "key conflict",
                       f"same {' + '.join(key)} as row {first_row} but different {', '.join(differing)}")
        else:
            log.reject(row, "exact duplicate", f"exact duplicate of row {first_row}")


def normalise(text, ignore_tokens=()):
    """Reduce a name or description to what matters for comparison.

    Lowercase, punctuation removed, ignored words (legal forms such as LTD)
    dropped, and words sorted so that word order does not matter.
    """
    ignore = {token.casefold() for token in ignore_tokens}
    words = _NON_WORD.sub(" ", text.casefold()).split()
    return " ".join(sorted(word for word in words if word not in ignore))


def similarity(a, b):
    """Similarity of two normalised texts, from 0 (nothing shared) to 1 (identical)."""
    return SequenceMatcher(None, a, b).ratio()


def near_duplicates(df, cfg, log):
    """Find rows whose text is almost the same as an earlier row's.

    Rows are compared only inside a block (same values in `block_by`), only if
    they differ in `distinct_on`, and only if the numbers in both texts are
    identical, so "BOLT M8X20" and "BOLT M8X25" are never treated as one item.
    """
    column = cfg["column"]
    block_by = cfg.get("block_by", [])
    distinct_on = cfg.get("distinct_on", [])
    ignore_tokens = cfg.get("ignore_tokens", [])
    kept = {}  # block -> [(row, normalised text, numbers, identity)]
    for row in df.index:
        if log.is_rejected(row):
            continue
        text = normalise(df.at[row, column], ignore_tokens)
        if not text:
            continue
        numbers = sorted(_NUMBERS.findall(text))
        identity = tuple(df.at[row, c] for c in distinct_on)
        candidates = kept.setdefault(tuple(df.at[row, c] for c in block_by), [])

        best_row, best_score = None, 0.0
        for other_row, other_text, other_numbers, other_identity in candidates:
            if numbers != other_numbers or (distinct_on and identity == other_identity):
                continue
            score = similarity(other_text, text)
            if score >= cfg["threshold"] and score > best_score:
                best_row, best_score = other_row, score

        if best_row is None:
            candidates.append((row, text, numbers, identity))
            continue
        message = f"near-duplicate of row {best_row} ({column} similarity {best_score:.2f})"
        if cfg.get("action", "reject") == "flag":
            log.flag(row, message)
        else:
            log.reject(row, "near-duplicate", message)
