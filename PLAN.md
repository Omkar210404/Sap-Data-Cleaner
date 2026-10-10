# PLAN — sap-data-cleaner

A Python CLI that cleans messy SAP-style master data exports (material master, vendor master) with pandas, driven by one YAML rules file per data type.

Status: **approved 2026-10-10**, with the planned defaults in section 13.

## 1. Environment (inspected 2026-10-10)

| Item | Found |
|------|-------|
| OS / shell | Windows 11, PowerShell |
| Python | 3.11.9 (Microsoft Store build, no `py` launcher) |
| Global packages | PyYAML 6.0.3 present; pandas, pytest **not** installed |
| Internet / PyPI | reachable (pandas 3.0.6 is the latest listed) |
| Git | 2.49.0, identity `Omkar210404 <omkarnikamofficial21@gmail.com>`, sibling repos use `main` |
| GPU | not needed |

Consequence: everything runs in a project-local `.venv` (git-ignored). Pins follow the sibling repos: `pandas==3.0.6`, `PyYAML==6.0.3`, `pytest` pinned to whatever version installs.

## 2. Scope

In: read one CSV, apply configured rules, write cleaned CSV + rejected CSV + text report.
Out: no SAP connection, no RFC/BAPI/LSMW upload, no GUI, no database, no ML. It is a flat-file pre-load cleaning tool.

## 3. Data model (simplified, SAP field names)

**Material** (`--type material`, loosely MARA/MAKT/MARC):
`MATNR` material number, `MAKTX` description, `MTART` material type, `MATKL` material group, `MEINS` base unit, `WERKS` plant, `BRGEW` gross weight, `GEWEI` weight unit, `ERSDA` created on.

**Vendor** (`--type vendor`, loosely LFA1/LFB1):
`LIFNR` vendor number, `NAME1` name, `ORT01` city, `PSTLZ` postal code, `LAND1` country, `STCD1` tax number, `KTOKK` account group, `ZTERM` payment terms, `WAERS` currency, `ERDAT` created on.

Every column is read as text (`dtype=str`, no NA inference) so leading zeros are never lost on the way in.

## 4. Rules

Rules run in this fixed order. Each rule is switched on/off and parameterised in YAML.

| # | Rule | What it does | Outcome |
|---|------|--------------|---------|
| 1 | `trim` | Strip leading/trailing whitespace, collapse internal runs of spaces, turn empty/`NULL`/`N/A`/`-` into blank | fix |
| 2 | `uppercase` | Uppercase the listed code columns (`MTART`, `MEINS`, `LAND1`, ...) | fix |
| 3 | `zero_pad` | Left-pad all-numeric IDs to a fixed width (`MATNR` 18, `LIFNR` 10); strip a trailing `.0` left by spreadsheets; alphanumeric IDs are uppercased, not padded | fix |
| 4 | `dates` | Parse a list of accepted input formats (`DD.MM.YYYY`, `YYYYMMDD`, `DD/MM/YYYY`, `YYYY-MM-DD`, ...) and write one output format | fix; unparseable or impossible date → reject |
| 5 | `unit_of_measure` | Map known aliases (`PCS`→`PC`, `KGS`→`KG`, `EACH`→`EA`, `ST`→`PC`, ...) then check against the reference list | fix; unknown unit → reject |
| 6 | `country` | Map aliases (`INDIA`→`IN`, `DEU`→`DE`, `UK`→`GB`, ...) then check against the ISO alpha-2 reference list | fix; unknown country → reject |
| 7 | `mandatory` | Per field: `reject` if blank, or `fill` with a configured default (e.g. blank `GEWEI` → `KG` when a weight is given) | fill (counted in report) or reject |
| 8 | `exact_duplicates` | After rules 1–7, rows identical on the configured key columns: keep the first, move the rest out. Same key but conflicting other values is reported as its own reason | reject with "exact duplicate of row N" / "key conflict with row N" |
| 9 | `near_duplicates` | Normalise the text column (lowercase, strip punctuation and legal suffixes like LTD/PVT/GMBH, sort tokens), compare within a block (vendors: same country; materials: same material type) and only between rows with different IDs, similarity ≥ threshold | reject-for-review with "near-duplicate of row N (score 0.xx)", or flag in place, per config |

Design points:

- A row collects **all** its reject reasons, not just the first, joined with `; `.
- Rejected rows are written with their **original** input values plus `SOURCE_ROW` and `REJECT_REASONS`, so they can be corrected at the source.
- Near-duplicates are never merged automatically. The first occurrence stays, the others go to the rejected file, which acts as the review queue.
- The numbers in two texts must match exactly for a near-duplicate, so `BOLT M8X20` and `BOLT M8X25` are not collapsed.
- The exact-duplicate key for materials is `MATNR` + `WERKS`, because one material legitimately exists in several plants.
- Similarity uses the standard library (`difflib.SequenceMatcher`), so there is no extra dependency.

## 5. Config

- `sap_cleaner/config/material.yaml`, `sap_cleaner/config/vendor.yaml` — columns, mandatory fields and actions, ID widths, date formats, duplicate keys, near-duplicate threshold and action.
- `sap_cleaner/config/reference.yaml` — units of measure, country codes, alias maps (the small built-in reference lists).
- `--config PATH` replaces the built-in file for that run.
- Config is validated on load: unknown rule names, unknown keys, or columns missing from the input give a clear error and a non-zero exit, not a traceback.

## 6. CLI

```
python -m sap_cleaner clean --input data/synthetic/materials.csv --type material --out out/
python -m sap_cleaner clean --input data/synthetic/vendors.csv   --type vendor   --out out/
```

| Option | Default | Purpose |
|--------|---------|---------|
| `--input` | required | CSV to clean |
| `--type` | required | `material` or `vendor` |
| `--out` | required | output directory, created if missing |
| `--config` | built-in | alternative rules YAML |
| `--delimiter` | `,` | SAP exports are often `;` or tab |
| `--encoding` | `utf-8-sig` | e.g. `cp1252` for older exports |

Outputs in `--out`: `<name>_cleaned.csv`, `<name>_rejected.csv`, `<name>_report.txt`, `<name>_changes.csv`.
`<name>_changes.csv` (one line per changed cell: row, column, old, new, rule) is an addition beyond the three requested outputs; it is what makes the report auditable and supplies the README before/after examples.

Exit codes: `0` ran to completion (even with rejects), `1` input file problem, `2` usage or config error.

The report lists: rows read / cleaned / rejected, cells changed per rule, values filled per field, rejects per reason, and a few example changes. All numbers are counted from the run.

## 7. Sample data

- `scripts/generate_sample_data.py`, fixed seed, standard library only, writes `data/synthetic/materials.csv` (about 40 rows) and `data/synthetic/vendors.csv` (about 30 rows).
- Starts from a clean invented base table, then injects named defects: stripped leading zeros, lowercase codes, padded whitespace, mixed date formats, an impossible date, unit aliases, an unknown unit, country names instead of codes, an unknown country, blank mandatory fields, exact duplicate rows, near-duplicate names/descriptions, and one "looks similar but is different" pair that must survive.
- Labelled synthetic in four places: the `synthetic/` folder name, `data/README.md`, the generator docstring, and the README. Vendor names are invented and obviously fictional. No real company data.
- The generator records how many of each defect it injected, so the end-to-end test asserts exact expected counts instead of "some rows were rejected".

## 8. File layout

```
sap-data-cleaner/
├── sap_cleaner/
│   ├── __init__.py
│   ├── __main__.py          # python -m sap_cleaner
│   ├── cli.py               # argparse, exit codes
│   ├── config.py            # load + validate YAML
│   ├── pipeline.py          # runs rules in order, builds the output tables
│   ├── runlog.py            # records every change and reject reason
│   ├── report.py            # text summary
│   ├── rules/
│   │   ├── standardise.py   # trim, uppercase, zero_pad
│   │   ├── dates.py
│   │   ├── reference.py     # unit_of_measure, country
│   │   ├── mandatory.py
│   │   └── duplicates.py    # exact + near
│   └── config/
│       ├── material.yaml
│       ├── vendor.yaml
│       └── reference.yaml
├── scripts/generate_sample_data.py
├── data/
│   ├── README.md            # "synthetic, generated by script"
│   └── synthetic/{materials,vendors}.csv, manifest.json
├── examples/output/         # committed outputs of a real run, used by the README
├── tests/
├── README.md  PLAN.md  LICENSE  .gitignore  .gitattributes  pytest.ini  requirements.txt
```

`out/`, `.venv/`, `__pycache__/`, `.pytest_cache/` are git-ignored.

## 9. Tests (pytest)

One test module per rule, small in-memory DataFrames, each asserting both the fixed value and the recorded change/reject reason:

| Module | Covers |
|--------|--------|
| `test_standardise.py` | trim and null tokens; uppercase only on listed columns; zero-pad numeric vs alphanumeric IDs, `.0` stripping, over-length ID |
| `test_dates.py` | each accepted format, day-first handling, impossible date rejected, blank date left to the mandatory rule |
| `test_reference.py` | unit aliases, unknown unit rejected; country aliases, unknown country rejected |
| `test_mandatory.py` | reject action, fill action, conditional fill, multiple reasons on one row |
| `test_duplicates.py` | exact duplicate keeps first; key conflict; near-duplicate above/below threshold; digits-differ pair not matched; blocking by country |
| `test_config.py` | built-in configs load; bad rule name and missing column give clear errors |
| `test_pipeline.py` | reading text without losing zeros, rule order, disabled rules, rejected rows kept as input, flag action |
| `test_report.py` | report counts equal the pipeline's counts |
| `test_cli_e2e.py` | **end-to-end**: generate sample data into a temp dir, run the CLI as a subprocess, check all output files exist, cleaned + rejected = input rows, expected reject counts per reason, no leading-zero loss, running the cleaner on its own cleaned output changes nothing, committed sample data and example outputs match a fresh run |

## 10. Commits

Small, one concern each, author identity as in the sibling repos, no `Co-Authored-By` or session lines:

1. Add PLAN.md, LICENSE, .gitignore, requirements.txt
2. Add synthetic sample data generator and generated files
3. Add config loader and built-in YAML rules
4. Add trim / uppercase / zero-pad rules with tests
5. Add date standardisation with tests
6. Add unit and country validation with tests
7. Add mandatory field rule with tests
8. Add exact and near-duplicate detection with tests
9. Add pipeline, report and CLI
10. Add end-to-end test
11. Add README with real before/after examples and example outputs

## 11. Risks and how they are handled

| Risk | Handling |
|------|----------|
| Leading zeros lost by type inference | Read and write everything as text; e2e test checks it |
| Ambiguous dates (`03/04/2024`) | Formats are an explicit ordered list in config, default day-first; no free-form guessing; unparseable → reject |
| Near-duplicate false positives | Blocking, numeric-token guard, configurable threshold, never auto-merged, a "must survive" pair in the sample data |
| Near-duplicate cost grows with rows² inside a block | Fine for small/medium files; stated as a limitation, no performance claims |
| "Keep first" keeps the wrong record of a duplicate pair | Stated as a limitation; the dropped row and its match are both named in the rejected file |
| pandas 3 string dtype / copy-on-write differences | Version pinned; rules written without chained assignment; tests run on the pinned version |
| Simplified schema is not a real SAP table extract | README says so plainly; column lists live in YAML, not code |
| Reference lists are small subsets | Labelled as subsets; extendable in `reference.yaml` |
| Delimiter / encoding of real exports | `--delimiter` and `--encoding` flags; only comma + UTF-8 is exercised by the sample data, and the README says that |

## 12. Deviations from brain.md checklist

- No `.env.example`: the tool has no secrets or API keys.
- No screenshots: CLI only, so the README shows real terminal output and real rows from `examples/output/`.
- A small Mermaid diagram of the pipeline will be in the README.
- This is a fourth project outside the three listed in `brain.md`; `brain.md` and `prompts/` stay untouched and outside this repo.

## 14. Added after the first build: local web page

Requested once the CLI was done. `python -m sap_cleaner serve` starts a page on `127.0.0.1` where a CSV can be uploaded, inspected tab by tab and the output files downloaded.

- Standard library `http.server` plus plain HTML/CSS/JS in `sap_cleaner/webui/`, so no new dependencies.
- The upload goes through the same pipeline as the CLI. `outputs.py` builds the output files for both, and a test checks they are identical.
- Nothing uploaded is written to disk. Local only, no login.
- `tests/test_web.py` runs the real server on a free port. The browser side was checked by a scripted run in Edge, which is not in the test suite.

## 13. Decisions (approved as planned)

1. **Near-duplicates default**: later occurrences move to the rejected file for review. `action: flag` keeps them in the cleaned file with a note column instead.
2. **Date output format**: ISO `YYYY-MM-DD`. SAP internal `YYYYMMDD` is one config line.
3. **`changes.csv` audit file**: kept as a fourth output.
