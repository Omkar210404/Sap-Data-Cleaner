"""Command line interface.

    python -m sap_cleaner clean --input FILE --type TYPE --out DIR
    python -m sap_cleaner serve
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import DATA_TYPES, ConfigError, load_config, load_reference
from .outputs import build_outputs
from .pipeline import InputError, clean, read_input

EXIT_OK, EXIT_INPUT_ERROR, EXIT_CONFIG_ERROR = 0, 1, 2
DEFAULT_PORT = 8765


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

    serve_cmd = commands.add_parser(
        "serve", help="open a local web page for trying the cleaner",
        description="Start a local web page where you can upload a CSV, see what the cleaner did "
                    "and download the results. Listens on this computer only. Stop it with Ctrl+C.")
    serve_cmd.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to listen on, default {DEFAULT_PORT}")
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
    rules_source = Path(args.config).as_posix() if args.config else f"built-in {args.type}.yaml"
    files = build_outputs(result, stem, delimiter, Path(args.input).as_posix(), args.type, rules_source)
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")

    shown = {kind: (out_dir / f"{stem}_{kind}").as_posix() for kind in ("cleaned", "rejected", "changes", "report")}
    print(f"Read {result.rows_read} rows from {Path(args.input).as_posix()} ({args.type})")
    print(f"  cleaned  {len(result.cleaned):>5} rows  -> {shown['cleaned']}.csv")
    print(f"  rejected {len(result.rejected):>5} rows  -> {shown['rejected']}.csv")
    print(f"  changes  {len(result.changes):>5} lines -> {shown['changes']}.csv")
    print(f"  report               -> {shown['report']}.txt")
    return EXIT_OK


def run_serve(args):
    from .web import make_server  # imported here so `clean` does not load the web code

    try:
        server = make_server(args.port)
    except OSError as error:
        raise InputError(f"could not start the web page on port {args.port}: {error}") from None
    print(f"sap_cleaner web page: http://127.0.0.1:{server.server_address[1]}/")
    print("Listening on this computer only. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        server.server_close()
    return EXIT_OK


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run_serve(args) if args.command == "serve" else run_clean(args)
    except ConfigError as error:
        print(f"Config error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except InputError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
