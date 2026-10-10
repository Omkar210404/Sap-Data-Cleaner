"""Load and validate the YAML rule files.

Validation is strict on purpose: a typo in a rule name or column should stop
the run with a readable message instead of silently skipping a rule.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent / "config"
DATA_TYPES = ("material", "vendor")

# The order rules run in. Standardising comes first so that validation and
# duplicate detection compare cleaned values.
RULE_ORDER = (
    "trim", "uppercase", "zero_pad", "dates", "unit_of_measure", "country",
    "mandatory", "exact_duplicates", "near_duplicates",
)

# rule name -> (required keys, optional keys). `enabled` is allowed everywhere.
RULE_KEYS = {
    "trim": (set(), {"null_tokens"}),
    "uppercase": ({"columns"}, set()),
    "zero_pad": ({"columns"}, {"allowed_pattern"}),
    "dates": ({"columns", "input_formats", "output_format"}, {"blank_values"}),
    "unit_of_measure": ({"columns"}, set()),
    "country": ({"columns"}, set()),
    "mandatory": ({"fields"}, set()),
    "exact_duplicates": ({"key"}, {"ignore_case"}),
    "near_duplicates": ({"column", "threshold"}, {"block_by", "distinct_on", "action", "ignore_tokens"}),
}


class ConfigError(Exception):
    """The rules file or reference file is missing, malformed or inconsistent."""


def _read_yaml(path):
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except yaml.YAMLError as error:
        raise ConfigError(f"{path} is not valid YAML: {error}") from None


def _string_list(value, where):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where} must be a list of quoted strings, got {value!r}")
    return value


def _referenced_columns(name, rule):
    """Every input column a rule mentions, so they can be checked against `columns`."""
    if name in ("uppercase", "dates", "unit_of_measure", "country"):
        return _string_list(rule["columns"], f"{name}.columns")
    if name == "zero_pad":
        if not isinstance(rule["columns"], dict):
            raise ConfigError("zero_pad.columns must map each column to a width")
        return list(rule["columns"])
    if name == "mandatory":
        if not isinstance(rule["fields"], dict):
            raise ConfigError("mandatory.fields must map each column to an action")
        conditions = [spec.get("when_present") for spec in rule["fields"].values() if isinstance(spec, dict)]
        return [*rule["fields"], *[c for c in conditions if c]]
    if name == "exact_duplicates":
        return _string_list(rule["key"], "exact_duplicates.key")
    if name == "near_duplicates":
        return [rule["column"],
                *_string_list(rule.get("block_by", []), "near_duplicates.block_by"),
                *_string_list(rule.get("distinct_on", []), "near_duplicates.distinct_on")]
    return []


def _check_rule(name, rule):
    if name == "trim":
        _string_list(rule.get("null_tokens", []), "trim.null_tokens")
    elif name == "zero_pad":
        for column, width in rule["columns"].items():
            if not isinstance(width, int) or isinstance(width, bool) or width < 1:
                raise ConfigError(f"zero_pad width for {column} must be a positive whole number")
        if "allowed_pattern" in rule:
            try:
                re.compile(rule["allowed_pattern"])
            except (re.error, TypeError):
                raise ConfigError("zero_pad.allowed_pattern is not a valid regular expression") from None
    elif name == "dates":
        _string_list(rule["input_formats"], "dates.input_formats")
        _string_list(rule.get("blank_values", []), "dates.blank_values")
        if not isinstance(rule["output_format"], str):
            raise ConfigError("dates.output_format must be a string such as \"%Y-%m-%d\"")
    elif name == "mandatory":
        for column, spec in rule["fields"].items():
            if not isinstance(spec, dict) or spec.get("action") not in ("reject", "fill"):
                raise ConfigError(f"mandatory.fields.{column} needs action: reject or action: fill")
            unknown = set(spec) - {"action", "value", "when_present"}
            if unknown:
                raise ConfigError(f"mandatory.fields.{column} has unknown keys: {sorted(unknown)}")
            if spec["action"] == "fill" and not (isinstance(spec.get("value"), str) and spec["value"]):
                raise ConfigError(
                    f"mandatory.fields.{column} uses action: fill, so it needs a quoted "
                    f"string value (for example value: \"0001\"), got {spec.get('value')!r}")
    elif name == "exact_duplicates":
        if not rule["key"]:
            raise ConfigError("exact_duplicates.key must list at least one column")
        if not isinstance(rule.get("ignore_case", True), bool):
            raise ConfigError("exact_duplicates.ignore_case must be true or false")
    elif name == "near_duplicates":
        threshold = rule["threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 < threshold <= 1:
            raise ConfigError("near_duplicates.threshold must be a number above 0 and at most 1")
        if rule.get("action", "reject") not in ("reject", "flag"):
            raise ConfigError("near_duplicates.action must be reject or flag")
        _string_list(rule.get("ignore_tokens", []), "near_duplicates.ignore_tokens")


def validate_config(config):
    """Raise ConfigError if the rules file cannot be used as it is."""
    if not isinstance(config, dict):
        raise ConfigError("the rules file must be a mapping with `columns` and `rules`")
    unknown = set(config) - {"data_type", "columns", "rules"}
    if unknown:
        raise ConfigError(f"unknown top-level keys: {sorted(unknown)}")
    columns = _string_list(config.get("columns"), "columns")
    if not columns:
        raise ConfigError("columns must list at least one column")
    rules = config.get("rules")
    if not isinstance(rules, dict):
        raise ConfigError("rules must be a mapping of rule name to settings")

    for name, rule in rules.items():
        if name not in RULE_KEYS:
            raise ConfigError(f"unknown rule '{name}'. Known rules: {', '.join(RULE_ORDER)}")
        if not isinstance(rule, dict):
            raise ConfigError(f"settings for rule '{name}' must be a mapping")
        required, optional = RULE_KEYS[name]
        missing = required - set(rule)
        if missing:
            raise ConfigError(f"rule '{name}' is missing: {sorted(missing)}")
        unknown = set(rule) - required - optional - {"enabled"}
        if unknown:
            raise ConfigError(f"rule '{name}' has unknown keys: {sorted(unknown)}")
        if not isinstance(rule.get("enabled", True), bool):
            raise ConfigError(f"rule '{name}': enabled must be true or false")
        for column in _referenced_columns(name, rule):
            if column not in columns:
                raise ConfigError(f"rule '{name}' uses column '{column}', which is not in `columns`")
        _check_rule(name, rule)
    return config


def load_config(data_type, path=None):
    """Return the validated rules for a data type, from `path` or the built-in file."""
    if data_type not in DATA_TYPES:
        raise ConfigError(f"unknown data type '{data_type}'. Choose from: {', '.join(DATA_TYPES)}")
    config = _read_yaml(path or CONFIG_DIR / f"{data_type}.yaml")
    validate_config(config)
    declared = config.get("data_type")
    if declared and declared != data_type:
        raise ConfigError(f"this rules file is for '{declared}' data, but --type is '{data_type}'")
    return config


def load_reference(path=None):
    """Return the built-in reference lists as {name: {"valid": set, "aliases": dict}}."""
    raw = _read_yaml(path or CONFIG_DIR / "reference.yaml")
    if not isinstance(raw, dict):
        raise ConfigError("the reference file must be a mapping of list name to entries")
    reference = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict) or "valid" not in entry:
            raise ConfigError(f"reference list '{name}' needs a `valid` list")
        valid = _string_list(entry["valid"], f"{name}.valid")
        aliases = entry.get("aliases") or {}
        for alias, code in aliases.items():
            if not isinstance(alias, str) or not isinstance(code, str):
                raise ConfigError(f"{name}.aliases: quote both sides of {alias!r}: {code!r}")
            if code not in valid:
                raise ConfigError(f"{name}.aliases maps '{alias}' to '{code}', which is not a valid code")
        reference[name] = {"valid": set(valid), "aliases": {a.upper(): c for a, c in aliases.items()}}
    return reference
