"""Record of what the rules did to each row.

Every output (cleaned file, rejected file, change log, report) is built from
this one log, so their numbers cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class RunLog:
    changes: list = field(default_factory=list)
    rejects: dict = field(default_factory=dict)   # row -> [(category, message), ...]
    flags: dict = field(default_factory=dict)     # row -> note, for rows kept but flagged

    def change(self, row, column, old, new, rule):
        self.changes.append({"row": row, "column": column, "old": old, "new": new, "rule": rule})

    def reject(self, row, category, message):
        """Mark a row as rejected. `category` groups reasons in the report."""
        self.rejects.setdefault(row, []).append((category, message))

    def flag(self, row, note):
        self.flags[row] = note

    def is_rejected(self, row):
        return row in self.rejects

    def reasons(self, row):
        """The full reject messages for a row, in the order they were found."""
        return [message for _, message in self.rejects.get(row, [])]

    def categories(self, row):
        return [category for category, _ in self.rejects.get(row, [])]


def apply_changes(df, column, new_values, rule, log):
    """Write new values (one per row, in order) into a column and log every cell that changed."""
    old_values = df[column]
    new_values = pd.Series(list(new_values), index=df.index, dtype=old_values.dtype)
    for row in df.index[old_values != new_values]:
        log.change(row, column, old_values[row], new_values[row], rule)
    df[column] = new_values
