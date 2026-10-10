import re

import pytest

from sap_cleaner.config import load_config, load_reference
from sap_cleaner.pipeline import clean
from sap_cleaner.report import build_report, summarise


def material(matnr, text, **overrides):
    row = {"MATNR": matnr, "MAKTX": text, "MTART": "ROH", "MATKL": "FASTENER", "MEINS": "PC",
           "WERKS": "1000", "BRGEW": "0.5", "GEWEI": "KG", "ERSDA": "2024-03-15"}
    return {**row, **overrides}


@pytest.fixture
def result(make_df):
    df = make_df([
        material("100001", "HEX BOLT M8X20", ERSDA="15.03.2024"),      # 2: zero_pad + dates
        material("100002", "hex nut m8", MEINS="pcs", GEWEI=""),       # 3: uppercase x2, zero_pad, unit, fill
        material("100003", "", MEINS="QQ"),                            # 4: rejected, two reasons
        material("100002", "HEX NUT M8", GEWEI=""),                    # 5: exact duplicate of row 3
        material("000000000000100004", "FLAT WASHER M8", MATKL=""),    # 6: fill
    ])
    return clean(df, load_config("material"), load_reference())


def test_summary_counts_match_the_output_tables(result):
    summary = summarise(result)
    assert summary["rows_read"] == 5
    assert summary["rows_cleaned"] == len(result.cleaned) == 3
    assert summary["rows_rejected"] == len(result.rejected) == 2
    assert summary["rows_cleaned"] + summary["rows_rejected"] == summary["rows_read"]
    assert summary["changes_total"] == len(result.changes)
    assert sum(summary["changes_by_rule"].values()) == summary["changes_total"]


def test_summary_breaks_changes_down_by_rule(result):
    assert summarise(result)["changes_by_rule"] == {
        "uppercase": 2, "zero_pad": 2, "dates": 1, "unit_of_measure": 1, "mandatory": 2,
    }


def test_summary_counts_fills_by_field(result):
    assert summarise(result)["fills_by_field"] == {"GEWEI": 1, "MATKL": 1}


def test_summary_counts_a_row_under_each_of_its_reasons(result):
    assert summarise(result)["rejects_by_reason"] == {
        "exact duplicate": 1,
        "missing mandatory field MAKTX": 1,
        "unknown unit of measure in MEINS": 1,
    }


def test_report_text_shows_the_same_numbers(result):
    text = build_report(result, "in.csv", "material", "built-in material.yaml")
    summary = summarise(result)
    assert "Input file : in.csv" in text
    assert re.search(r"Read\s+5\n", text)
    assert re.search(r"Cleaned\s+3\n", text)
    assert re.search(r"Rejected\s+2\n", text)
    assert re.search(rf"Total\s+{summary['changes_total']}\n", text)
    for label, count in {**summary["changes_by_rule"], **summary["rejects_by_reason"]}.items():
        assert re.search(rf"{re.escape(label)}\s+{count}\n", text)
    assert "'100001' -> '000000000000100001'  (zero_pad)" in text


def test_report_for_a_clean_file_says_none(make_df):
    df = make_df([material("000000000000100001", "HEX BOLT M8X20")])
    clean_result = clean(df, load_config("material"), load_reference())
    text = build_report(clean_result, "in.csv", "material", "built-in material.yaml")
    assert clean_result.changes.empty and clean_result.rejected.empty
    assert text.count("  none") == 3
