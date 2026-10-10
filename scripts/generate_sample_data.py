"""Generate SYNTHETIC messy SAP-style master data for sap-data-cleaner.

Everything this script writes is invented: material numbers, descriptions,
vendor names, tax numbers and dates. No real company data is used, and any
resemblance of a vendor name to a real company is coincidental.

The script builds a clean table, then injects named data-quality defects into
it. It also writes manifest.json, which records what was injected and which
rows are expected to be rejected, so the end-to-end test can check the cleaner
against the generator instead of against itself.

Usage:
    python scripts/generate_sample_data.py [--out data/synthetic] [--seed 42]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "synthetic"
DEFAULT_SEED = 42

MATERIAL_COLUMNS = ["MATNR", "MAKTX", "MTART", "MATKL", "MEINS", "WERKS", "BRGEW", "GEWEI", "ERSDA"]
VENDOR_COLUMNS = ["LIFNR", "NAME1", "ORT01", "PSTLZ", "LAND1", "STCD1", "KTOKK", "ZTERM", "WAERS", "ERDAT"]

DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%Y%m%d", "%d/%m/%Y"]

# (description, material type, material group, base unit, gross weight)
MATERIALS = [
    ("HEX BOLT M8X20 ZINC PLATED", "ROH", "FASTENER", "PC", "0.012"),
    ("HEX BOLT M8X25 ZINC PLATED", "ROH", "FASTENER", "PC", "0.014"),
    ("HEX NUT M8 ZINC PLATED", "ROH", "FASTENER", "PC", "0.005"),
    ("FLAT WASHER M8 STAINLESS", "ROH", "FASTENER", "PC", "0.002"),
    ("BALL BEARING 6204 2RS", "ERSA", "BEARING", "EA", "0.106"),
    ("BALL BEARING 6205 2RS", "ERSA", "BEARING", "EA", "0.128"),
    ("V-BELT A42", "ERSA", "DRIVE", "EA", "0.150"),
    ("HYDRAULIC OIL ISO VG 46", "HIBE", "LUBRICANT", "L", "0.870"),
    ("GEAR OIL EP 90", "HIBE", "LUBRICANT", "L", "0.900"),
    ("LITHIUM GREASE EP2", "HIBE", "LUBRICANT", "KG", "1.000"),
    ("COPPER WIRE 2.5 SQMM", "ROH", "ELECTRIC", "M", "0.022"),
    ("PVC CONDUIT PIPE 25MM", "ROH", "ELECTRIC", "M", "0.110"),
    ("MCB 16A SINGLE POLE", "ERSA", "ELECTRIC", "EA", "0.095"),
    ("CONTACTOR 32A 3 POLE", "ERSA", "ELECTRIC", "EA", "0.420"),
    ("INDUCTION MOTOR 5HP 3 PHASE", "ERSA", "ELECTRIC", "EA", "38.000"),
    ("NITRILE SAFETY GLOVES", "HIBE", "SAFETY", "BOX", "0.650"),
    ("SAFETY HELMET YELLOW", "HIBE", "SAFETY", "EA", "0.380"),
    ("WELDING ROD E6013 3.15MM", "HIBE", "WELDING", "KG", "1.000"),
    ("CUTTING DISC 4 INCH", "HIBE", "WELDING", "EA", "0.045"),
    ("ENAMEL PAINT WHITE", "HIBE", "PAINT", "L", "1.250"),
    ("NC THINNER", "HIBE", "PAINT", "L", "0.880"),
    ("CARTON BOX 300X200X150", "VERP", "PACKING", "EA", "0.210"),
    ("STRETCH FILM 500MM", "VERP", "PACKING", "ROL", "2.400"),
    ("CR STEEL SHEET 1.2MM", "ROH", "METAL", "KG", "1.000"),
    ("ALUMINIUM ROUND BAR 20MM", "ROH", "METAL", "KG", "1.000"),
    ("RUBBER GASKET 50MM", "ERSA", "SEAL", "EA", "0.018"),
    ("O-RING 30X3 NBR", "ERSA", "SEAL", "EA", "0.003"),
    ("FILTER ELEMENT 10 MICRON", "ERSA", "FILTER", "EA", "0.340"),
    ("PRESSURE GAUGE 0-10 BAR", "ERSA", "INSTRUM", "EA", "0.260"),
    ("LIMIT SWITCH ROLLER TYPE", "ERSA", "ELECTRIC", "EA", "0.120"),
]

# (name, city, postal code, country, account group, currency, payment terms)
VENDORS = [
    ("Zentrix Bearings Pvt Ltd", "Pune", "411019", "IN", "ZDOM", "INR", "NT30"),
    ("Kavora Industrial Supplies", "Mumbai", "400072", "IN", "ZDOM", "INR", "NT45"),
    ("Sundara Steel Traders", "Ahmedabad", "380015", "IN", "ZDOM", "INR", "NT30"),
    ("Sundara Steel Traders", "Dubai", "", "AE", "ZIMP", "AED", "NT60"),
    ("Orbita Electricals Pvt Ltd", "Bengaluru", "560058", "IN", "ZDOM", "INR", "NT30"),
    ("Rasika Rubber Works", "Kochi", "682030", "IN", "ZDOM", "INR", "NT45"),
    ("Velmora Packaging Solutions", "Chennai", "600032", "IN", "ZDOM", "INR", "NT30"),
    ("Dhruvika Fasteners", "Ludhiana", "141003", "IN", "ZDOM", "INR", "NT30"),
    ("Bluepeak Lubricants GmbH", "Hamburg", "20457", "DE", "ZIMP", "EUR", "NT60"),
    ("Brennfeld Hydraulik AG", "Stuttgart", "70565", "DE", "ZIMP", "EUR", "NT60"),
    ("Kestrelle Automation GmbH", "Munich", "80331", "DE", "ZIMP", "EUR", "NT45"),
    ("Marlowe & Finch Packaging Ltd", "Manchester", "M2 5BQ", "GB", "ZIMP", "GBP", "NT45"),
    ("Greywater Logistics Ltd", "Leeds", "LS1 4AP", "GB", "ZSRV", "GBP", "NT30"),
    ("Tamsin Tools Inc", "Chicago", "60601", "US", "ZIMP", "USD", "NT60"),
    ("Pinecrest Polymers LLC", "Houston", "77002", "US", "ZIMP", "USD", "NT60"),
    ("Quillon Safety Products Inc", "Columbus", "43215", "US", "ZIMP", "USD", "NT45"),
    ("Lumenfield Cables Pte Ltd", "Singapore", "609916", "SG", "ZIMP", "SGD", "NT45"),
    ("Hoshikawa Precision Co Ltd", "Osaka", "530-0001", "JP", "ZIMP", "JPY", "NT60"),
    ("Jinhai Metal Products Co Ltd", "Ningbo", "315000", "CN", "ZIMP", "CNY", "NT60"),
    ("Colles Aurelienne SAS", "Lyon", "69003", "FR", "ZIMP", "EUR", "NT45"),
    ("Noordwal Filters BV", "Rotterdam", "3011 AA", "NL", "ZIMP", "EUR", "NT45"),
    ("Al Rimal Industrial Trading LLC", "Sharjah", "", "AE", "ZIMP", "AED", "NT60"),
    ("Vantora Chemicals Pvt Ltd", "Vadodara", "390010", "IN", "ZDOM", "INR", "NT30"),
    ("Meghna Weld Consumables", "Faridabad", "121003", "IN", "ZSRV", "INR", "NT30"),
]

UNIT_ALIASES = {"PC": ["PCS", "ST"], "EA": ["EACH", "NOS"], "KG": ["KGS"], "L": ["LTR"], "M": ["MTR"]}
COUNTRY_ALIASES = {"IN": ["India", "IND"], "DE": ["Germany", "DEU"], "US": ["USA", "United States"], "GB": ["UK"]}


class Row(dict):
    """A CSV row plus bookkeeping about the defects injected into it."""

    def __init__(self, values):
        super().__init__(values)
        self.defects = []        # every defect injected, for the manifest counts
        self.reject_for = []     # defects that should make the cleaner reject the row
        self.duplicate_of = None  # the Row this one duplicates, if any
        self.must_survive = False


def random_date(rng):
    start = date(2019, 1, 1)
    return start + timedelta(days=rng.randrange((date(2024, 12, 31) - start).days))


def tag(row, defect, reject=False):
    row.defects.append(defect)
    if reject:
        row.reject_for.append(defect)


def pad_text(rng, text):
    """Return the text with whitespace noise that trimming should remove."""
    return rng.choice([f"  {text}", f"{text}   ", text.replace(" ", "  ", 1), f" {text} "])


def insert_after(rng, rows, original, new_row):
    """Insert new_row at a random position somewhere below its original."""
    position = next(i for i, row in enumerate(rows) if row is original)
    rows.insert(rng.randint(position + 1, len(rows)), new_row)


def add_cosmetic_defects(rng, rows, id_column, text_columns, code_columns, date_column):
    """Defects the cleaner should fix without rejecting the row."""
    for row in rows:
        fmt = rng.choice(DATE_FORMATS)
        if fmt != DATE_FORMATS[0]:
            row[date_column] = date.fromisoformat(row[date_column]).strftime(fmt)
            tag(row, "date_in_other_format")
        if row[id_column].isdigit() and rng.random() < 0.6:
            row[id_column] = row[id_column].lstrip("0")
            tag(row, "leading_zeros_stripped")
    for row in rng.sample(rows, 6):
        column = rng.choice(text_columns)
        if row[column]:
            row[column] = pad_text(rng, row[column])
            tag(row, "extra_whitespace")
    for row in rng.sample(rows, 6):
        for column in code_columns:
            row[column] = row[column].lower()
        tag(row, "lowercase_codes")


def build_materials(rng):
    rows = []
    for number, (text, mtart, matkl, meins, weight) in enumerate(MATERIALS, start=100001):
        rows.append(Row({
            "MATNR": str(number).zfill(18), "MAKTX": text, "MTART": mtart, "MATKL": matkl,
            "MEINS": meins, "WERKS": rng.choice(["1000", "2000"]), "BRGEW": weight, "GEWEI": "KG",
            "ERSDA": random_date(rng).isoformat(),
        }))
    by_text = {row["MAKTX"]: row for row in rows}

    # Alphanumeric IDs must be left unpadded by the cleaner.
    by_text["FILTER ELEMENT 10 MICRON"]["MATNR"] = "SP-4410"
    by_text["PRESSURE GAUGE 0-10 BAR"]["MATNR"] = "SP-4411"

    # Looks similar, but the numbers differ: two real, different materials.
    for text in ("HEX BOLT M8X20 ZINC PLATED", "HEX BOLT M8X25 ZINC PLATED"):
        by_text[text].must_survive = True

    # The same material extended to a second plant is legitimate, not a duplicate.
    for text in ("HEX NUT M8 ZINC PLATED", "GEAR OIL EP 90"):
        original = by_text[text]
        original.must_survive = True
        second_plant = Row({**original, "WERKS": "2000" if original["WERKS"] == "1000" else "1000"})
        second_plant.must_survive = True
        tag(second_plant, "same_material_other_plant")
        rows.append(second_plant)

    duplicate_sources = ["LITHIUM GREASE EP2", "CARTON BOX 300X200X150"]
    conflict_source = "SAFETY HELMET YELLOW"
    near_duplicates = {
        "BALL BEARING 6204 2RS": "BEARING BALL 6204 2RS",
        "HYDRAULIC OIL ISO VG 46": "HYDRALIC OIL ISO VG 46",
        "NITRILE SAFETY GLOVES": "Nitrile Safety Gloves.",
    }
    protected = {id(row) for row in rows if row.must_survive}
    protected |= {id(by_text[t]) for t in [*duplicate_sources, conflict_source, *near_duplicates]}

    add_cosmetic_defects(rng, rows, "MATNR", ["MAKTX"], ["MTART", "MEINS"], "ERSDA")

    for row in rng.sample([r for r in rows if r["MEINS"].upper() in UNIT_ALIASES], 6):
        row["MEINS"] = rng.choice(UNIT_ALIASES[row["MEINS"].upper()])
        tag(row, "unit_alias")
    for row in rng.sample(rows, 3):
        row["GEWEI"] = ""
        tag(row, "blank_weight_unit_fillable")
    for row in rng.sample(rows, 2):
        row["MATKL"] = ""
        tag(row, "blank_material_group_fillable")
    no_weight = by_text["LIMIT SWITCH ROLLER TYPE"]
    no_weight["BRGEW"], no_weight["GEWEI"] = "N/A", ""
    tag(no_weight, "null_token")
    float_id = by_text["V-BELT A42"]
    float_id["MATNR"] = float_id["MATNR"].lstrip("0") + ".0"
    tag(float_id, "spreadsheet_float_id")

    # Defects that must send the row to the rejected file.
    pool = [row for row in rows if id(row) not in protected and row not in (no_weight, float_id)]
    victims = rng.sample(pool, 7)
    victims[0]["MAKTX"] = ""
    tag(victims[0], "missing_MAKTX", reject=True)
    victims[1]["MEINS"] = ""
    tag(victims[1], "missing_MEINS", reject=True)
    victims[2]["MTART"] = ""
    tag(victims[2], "missing_MTART", reject=True)
    victims[2]["MEINS"] = "QQ"
    tag(victims[2], "unknown_unit", reject=True)
    victims[3]["MEINS"] = "XX"
    tag(victims[3], "unknown_unit", reject=True)
    victims[4]["ERSDA"] = "31.02.2023"
    tag(victims[4], "invalid_date", reject=True)
    victims[5]["ERSDA"] = "TBD"
    tag(victims[5], "invalid_date", reject=True)
    victims[6]["MATNR"] = "1.00045E+5"
    tag(victims[6], "invalid_id", reject=True)

    # Duplicates are copied from the messy original, then made to look different.
    for text in duplicate_sources:
        original = by_text[text]
        copy = Row({**original, "MAKTX": f" {original['MAKTX'].strip().lower()}  ",
                    "MATNR": original["MATNR"].lstrip("0")})
        copy.duplicate_of = original
        tag(copy, "exact_duplicate", reject=True)
        insert_after(rng, rows, original, copy)
    original = by_text[conflict_source]
    conflict = Row({**original, "MEINS": "BOX"})
    conflict.duplicate_of = original
    tag(conflict, "key_conflict", reject=True)
    insert_after(rng, rows, original, conflict)
    for number, (text, variant) in enumerate(near_duplicates.items(), start=100101):
        original = by_text[text]
        near = Row({**original, "MATNR": str(number), "MAKTX": variant,
                    "ERSDA": random_date(rng).isoformat()})
        near.duplicate_of = original
        tag(near, "near_duplicate", reject=True)
        insert_after(rng, rows, original, near)
    return rows


def build_vendors(rng):
    rows = []
    for number, (name, city, postal, country, group, currency, terms) in enumerate(VENDORS, start=200001):
        rows.append(Row({
            "LIFNR": str(number).zfill(10), "NAME1": name, "ORT01": city, "PSTLZ": postal,
            "LAND1": country, "STCD1": f"SYN{rng.randrange(10**8):08d}", "KTOKK": group,
            "ZTERM": terms, "WAERS": currency, "ERDAT": random_date(rng).isoformat(),
        }))
    by_key = {(row["NAME1"], row["LAND1"]): row for row in rows}

    # Same name in a different country is treated as a different vendor.
    for key in (("Sundara Steel Traders", "IN"), ("Sundara Steel Traders", "AE")):
        by_key[key].must_survive = True

    duplicate_sources = [("Tamsin Tools Inc", "US"), ("Lumenfield Cables Pte Ltd", "SG")]
    conflict_source = ("Colles Aurelienne SAS", "FR")
    near_duplicates = {
        ("Zentrix Bearings Pvt Ltd", "IN"): "Zentrix Bearings Private Limited",
        ("Kavora Industrial Supplies", "IN"): "Kavora Industrial Suplies",
        ("Marlowe & Finch Packaging Ltd", "GB"): "Finch & Marlowe Packaging Limited",
        ("Bluepeak Lubricants GmbH", "DE"): "BLUEPEAK LUBRICANTS GMBH.",
    }
    protected = {id(row) for row in rows if row.must_survive}
    protected |= {id(by_key[k]) for k in [*duplicate_sources, conflict_source, *near_duplicates]}

    add_cosmetic_defects(rng, rows, "LIFNR", ["NAME1", "ORT01"], ["LAND1", "WAERS"], "ERDAT")

    for row in rng.sample([r for r in rows if r["LAND1"].upper() in COUNTRY_ALIASES], 7):
        row["LAND1"] = rng.choice(COUNTRY_ALIASES[row["LAND1"].upper()])
        tag(row, "country_alias")
    for row in rng.sample(rows, 3):
        row["ZTERM"] = ""
        tag(row, "blank_payment_terms_fillable")
    for row in rng.sample(rows, 2):
        row["STCD1"] = "-"
        tag(row, "null_token")
    initial_date = by_key[("Noordwal Filters BV", "NL")]
    initial_date["ERDAT"] = "00000000"
    tag(initial_date, "sap_initial_date")

    pool = [row for row in rows if id(row) not in protected and row is not initial_date]
    victims = rng.sample(pool, 6)
    victims[0]["NAME1"] = ""
    tag(victims[0], "missing_NAME1", reject=True)
    victims[1]["LAND1"] = ""
    tag(victims[1], "missing_LAND1", reject=True)
    victims[2]["KTOKK"] = ""
    tag(victims[2], "missing_KTOKK", reject=True)
    victims[3]["ORT01"] = ""
    tag(victims[3], "missing_ORT01", reject=True)
    victims[3]["LAND1"] = "ZZ"
    tag(victims[3], "unknown_country", reject=True)
    victims[4]["LAND1"] = "Atlantis"
    tag(victims[4], "unknown_country", reject=True)
    victims[5]["ERDAT"] = "2023-13-05"
    tag(victims[5], "invalid_date", reject=True)

    for key in duplicate_sources:
        original = by_key[key]
        copy = Row({**original, "NAME1": f"{original['NAME1'].strip().upper()} ",
                    "LIFNR": original["LIFNR"].lstrip("0")})
        copy.duplicate_of = original
        tag(copy, "exact_duplicate", reject=True)
        insert_after(rng, rows, original, copy)
    original = by_key[conflict_source]
    conflict = Row({**original, "ORT01": "Marseille"})
    conflict.duplicate_of = original
    tag(conflict, "key_conflict", reject=True)
    insert_after(rng, rows, original, conflict)
    for number, (key, variant) in enumerate(near_duplicates.items(), start=200101):
        original = by_key[key]
        near = Row({**original, "LIFNR": str(number), "NAME1": variant,
                    "STCD1": f"SYN{rng.randrange(10**8):08d}", "ERDAT": random_date(rng).isoformat()})
        near.duplicate_of = original
        tag(near, "near_duplicate", reject=True)
        insert_after(rng, rows, original, near)
    return rows


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def describe(filename, rows):
    """Manifest entry. Row numbers count the header as row 1, like a spreadsheet."""
    source_row = {id(row): number for number, row in enumerate(rows, start=2)}
    expected = []
    for row in rows:
        if row.reject_for:
            entry = {"row": source_row[id(row)], "defects": row.reject_for}
            if row.duplicate_of is not None:
                entry["of_row"] = source_row[id(row.duplicate_of)]
            expected.append(entry)
    return {
        "file": filename,
        "rows": len(rows),
        "defect_counts": dict(sorted(Counter(d for row in rows for d in row.defects).items())),
        "expected_rejects": expected,
        "must_survive_rows": [source_row[id(row)] for row in rows if row.must_survive],
    }


def generate(out_dir, seed=DEFAULT_SEED):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    materials = build_materials(rng)
    vendors = build_vendors(rng)
    write_csv(out_dir / "materials.csv", MATERIAL_COLUMNS, materials)
    write_csv(out_dir / "vendors.csv", VENDOR_COLUMNS, vendors)
    manifest = {
        "note": "SYNTHETIC DATA. Generated by scripts/generate_sample_data.py. Not real company data.",
        "seed": seed,
        "materials": describe("materials.csv", materials),
        "vendors": describe("vendors.csv", vendors),
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic messy SAP-style sample data.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed")
    args = parser.parse_args()
    manifest = generate(args.out, args.seed)
    for name in ("materials", "vendors"):
        entry = manifest[name]
        print(f"{entry['file']}: {entry['rows']} rows, "
              f"{len(entry['expected_rejects'])} expected rejects (SYNTHETIC)")
    print(f"Written to {Path(os.path.relpath(args.out)).as_posix()}")


if __name__ == "__main__":
    main()
