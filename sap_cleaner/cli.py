"""Command line interface: python -m sap_cleaner clean --input FILE --type TYPE --out DIR"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import DATA_TYPES, ConfigError, load_config, load_reference
from .pipeline import InputError, clean, read_input
from .report import build_report

EXIT_OK, EXIT_INPUT_ERROR, EXIT_CONFIG_ERROR = 0, 1, 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m sap_cleaner",
        description="Clean messy SAP-style master data exports (material and vendor master).")
    parser.add_argument("--version", action="version", version=f"sap_cleaner {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    clean_cmd = commands.add_parser(
        "clean", help="clean one CSV export",
        description="Clean one CSV export. Writes <name>_cleaned.csv, <name>_rejected.csv, "
                    "<name>_changes.csv and <name>_report.txt into the output directory.")
    clean_cmd.add_argument("--input", required=True, help="CSV file to clean")
    clean_cmd.add_argument("--type", required=True, choices=DATA_TYPES, help="kind of master data")
    clean_cmd.add_argument("--out", required=True, help="output directory (created if missing)")
    clean_cmd.add_argument("--config", help="rules YAML to use instead of the built-in one")
    clean_cmd.add_argument("--delimiter", default=",", help="field separator, default ','. Use '\\t' for tab")
    clean_cmd.add_argument("--encoding", default="utf-8-sig", help="input encoding, default utf-8-sig")
    return parser


def run_clean(args):
    delimiter = "\t" if args.delimiter == "\\t" else args.delimiter
    config = load_config(args.type, args.config)
    reference = load_reference()
    result = clean(read_input(args.input, delimiter, args.encoding), config, reference)

    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise InputError(f"cannot use output directory {out_dir}: {error}") from None
    stem = Path(args.input).stem
    paths = {kind: out_dir / f"{stem}_{kind}.csv" for kind in ("cleaned", "rejected", "changes")}
    paths["report"] = out_dir / f"{stem}_report.txt"

    for kind in ("cleaned", "rejected", "changes"):
        getattr(result, kind).to_csv(paths[kind], index=False, sep=delimiter,
                                     encoding="utf-8", lineterminator="\n")
    rules_source = Path(args.config).as_posix() if args.config else f"built-in {args.type}.yaml"
    report = build_report(result, Path(args.input).as_posix(), args.type, rules_source)
    paths["report"].write_text(report, encoding="utf-8", newline="\n")

    print(f"Read {result.rows_read} rows from {Path(args.input).as_posix()} ({args.type})")
    print(f"  cleaned  {len(result.cleaned):>5} rows  -> {paths['cleaned'].as_posix()}")
    print(f"  rejected {len(result.rejected):>5} rows  -> {paths['rejected'].as_posix()}")
    print(f"  changes  {len(result.changes):>5} cells -> {paths['changes'].as_posix()}")
    print(f"  report               -> {paths['report'].as_posix()}")
    return EXIT_OK


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run_clean(args)
    except ConfigError as error:
        print(f"Config error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except InputError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
