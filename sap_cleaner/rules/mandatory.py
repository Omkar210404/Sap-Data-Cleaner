"""Mandatory fields: fill a blank with a configured default, or reject the row."""

from __future__ import annotations

from ..runlog import apply_changes


def mandatory(df, cfg, log):
    for column, spec in cfg["fields"].items():
        blank = df[column] == ""
        if spec["action"] == "fill":
            # `when_present` limits the fill to rows where another field has a value,
            # e.g. only default the weight unit if a weight was entered.
            if spec.get("when_present"):
                blank &= df[spec["when_present"]] != ""
            apply_changes(df, column, df[column].mask(blank, spec["value"]), "mandatory", log)
        else:
            for row in df.index[blank]:
                log.reject(row, f"missing mandatory field {column}", f"{column} is blank")
