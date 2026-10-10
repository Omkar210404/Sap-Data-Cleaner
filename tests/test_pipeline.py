import copy

import pytest

from sap_cleaner.config import load_config, load_reference
from sap_cleaner.pipeline import NEAR_DUPLICATE_NOTE, InputError, clean, read_input


@pytest.fixture(scope="module")
def reference():
    return load_reference()


@pytest.fixture
def vendor_config():
    return copy.deepcopy(load_config("vendor"))


def vendor_row(**overrides):
    row = {"LIFNR": "200014", "NAME1": "Tamsin Tools Inc", "ORT01": "Chicago", "PSTLZ": "60601",
           "LAND1": "US", "STCD1": "SYN08135295", "KTOKK": "ZIMP", "ZTERM": "NT60", "WAERS": "USD",
           "ERDAT": "2023-07-08"}
    return {**row, **overrides}


def test_read_input_keeps_text_exactly_as_written(tmp_path):
    path = tmp_path / "in.csv"
    path.write_text("LIFNR,LAND1,PSTLZ\n0000200014,NA,\n007,NULL,01234\n", encoding="utf-8")
    df = read_input(path)
    assert df.index.tolist() == [2, 3]
    assert df.loc[2].tolist() == ["0000200014", "NA", ""]
    assert df.loc[3].tolist() == ["007", "NULL", "01234"]


def test_read_input_handles_bom_delimiter_and_header_spaces(tmp_path):
    path = tmp_path / "in.csv"
    path.write_bytes("﻿LIFNR; NAME1 \n0000200014;Müller GmbH\n".encode("utf-8"))
    df = read_input(path, delimiter=";")
    assert df.columns.tolist() == ["LIFNR", "NAME1"]
    assert df.at[2, "NAME1"] == "Müller GmbH"


def test_read_input_reports_a_missing_file(tmp_path):
    with pytest.raises(InputError, match="not found"):
        read_input(tmp_path / "nope.csv")


def test_missing_required_column_is_an_input_error(make_df, vendor_config, reference):
    row = vendor_row()
    del row["KTOKK"]
    with pytest.raises(InputError, match="missing columns the rules need: KTOKK"):
        clean(make_df([row]), vendor_config, reference)


def test_duplicates_are_compared_after_standardising(make_df, vendor_config, reference):
    # Same vendor, written two different ways. Only the standardised values match.
    df = make_df([vendor_row(), vendor_row(LIFNR="0000200014", LAND1="usa", ERDAT="08.07.2023")])
    result = clean(df, vendor_config, reference)
    assert result.cleaned.index.tolist() == [2]
    assert result.rejected["REJECT_REASONS"].tolist() == ["exact duplicate of row 2"]


def test_rejected_rows_keep_their_original_values(make_df, vendor_config, reference):
    df = make_df([vendor_row(NAME1="  Tamsin Tools Inc ", LAND1="Atlantis")])
    result = clean(df, vendor_config, reference)
    assert result.cleaned.empty
    rejected = result.rejected.iloc[0]
    assert rejected["SOURCE_ROW"] == 2
    assert rejected["NAME1"] == "  Tamsin Tools Inc "
    assert rejected["LIFNR"] == "200014"
    assert result.changes.empty


def test_changes_list_every_fix_made_to_a_cleaned_row(make_df, vendor_config, reference):
    result = clean(make_df([vendor_row(LAND1="us", ZTERM="")]), vendor_config, reference)
    assert result.changes.values.tolist() == [
        [2, "LIFNR", "200014", "0000200014", "zero_pad"],
        [2, "LAND1", "us", "US", "country"],
        [2, "ZTERM", "", "0001", "mandatory"],
    ]


def test_a_disabled_rule_does_not_run(make_df, vendor_config, reference):
    vendor_config["rules"]["zero_pad"]["enabled"] = False
    del vendor_config["rules"]["country"]
    result = clean(make_df([vendor_row(LAND1="Atlantis")]), vendor_config, reference)
    assert "zero_pad" not in result.rules_run and "country" not in result.rules_run
    assert result.cleaned.at[2, "LIFNR"] == "200014"
    assert result.cleaned.at[2, "LAND1"] == "Atlantis"


def test_flag_action_keeps_near_duplicates_with_a_note(make_df, vendor_config, reference):
    vendor_config["rules"]["near_duplicates"]["action"] = "flag"
    df = make_df([vendor_row(), vendor_row(LIFNR="200101", NAME1="TAMSIN TOOLS, INC.")])
    result = clean(df, vendor_config, reference)
    assert result.rejected.empty
    assert result.cleaned[NEAR_DUPLICATE_NOTE].tolist() == ["", "near-duplicate of row 2 (NAME1 similarity 1.00)"]


def test_extra_columns_pass_through_trimmed(make_df, vendor_config, reference):
    result = clean(make_df([vendor_row(TELF1=" 555 0100 ")]), vendor_config, reference)
    assert result.cleaned.columns[-1] == "TELF1"
    assert result.cleaned.at[2, "TELF1"] == "555 0100"


def test_input_with_no_data_rows_gives_empty_outputs(make_df, vendor_config, reference):
    df = make_df([vendor_row()]).iloc[0:0]
    result = clean(df, vendor_config, reference)
    assert result.rows_read == 0
    assert result.cleaned.empty and result.rejected.empty and result.changes.empty
