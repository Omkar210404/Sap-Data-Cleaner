from datetime import date

import pytest

from sap_cleaner.rules.dates import parse_date, standardise_dates

FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%Y%m%d", "%d/%m/%Y", "%d-%m-%Y"]
CFG = {
    "columns": ["ERSDA"],
    "input_formats": FORMATS,
    "output_format": "%Y-%m-%d",
    "blank_values": ["00000000", "00.00.0000"],
}


@pytest.mark.parametrize("raw", ["2024-03-15", "15.03.2024", "20240315", "15/03/2024", "15-03-2024"])
def test_each_accepted_format_becomes_iso(make_df, log, raw):
    df = make_df([{"ERSDA": raw}])
    standardise_dates(df, CFG, log)
    assert df.at[2, "ERSDA"] == "2024-03-15"
    assert not log.rejects


def test_day_comes_before_month(make_df, log):
    df = make_df([{"ERSDA": "03/04/2024"}])
    standardise_dates(df, CFG, log)
    assert df.at[2, "ERSDA"] == "2024-04-03"


def test_single_digit_day_and_month_are_accepted(make_df, log):
    df = make_df([{"ERSDA": "3.4.2024"}])
    standardise_dates(df, CFG, log)
    assert df.at[2, "ERSDA"] == "2024-04-03"


@pytest.mark.parametrize("raw", ["31.02.2023", "2023-13-05", "TBD", "15/03/24", "2024315"])
def test_values_that_are_not_dates_are_rejected(make_df, log, raw):
    df = make_df([{"ERSDA": raw}])
    standardise_dates(df, CFG, log)
    assert log.categories(2) == ["invalid date in ERSDA"]
    assert log.reasons(2) == [f"ERSDA '{raw}' is not a valid date"]
    assert df.at[2, "ERSDA"] == raw


def test_blank_date_is_left_for_the_mandatory_rule(make_df, log):
    df = make_df([{"ERSDA": ""}])
    standardise_dates(df, CFG, log)
    assert df.at[2, "ERSDA"] == ""
    assert not log.rejects
    assert not log.changes


def test_sap_initial_date_becomes_blank(make_df, log):
    df = make_df([{"ERSDA": "00000000"}])
    standardise_dates(df, CFG, log)
    assert df.at[2, "ERSDA"] == ""
    assert not log.rejects
    assert log.changes[0]["rule"] == "dates"


def test_output_format_is_configurable(make_df, log):
    df = make_df([{"ERSDA": "15.03.2024"}])
    standardise_dates(df, {**CFG, "output_format": "%Y%m%d"}, log)
    assert df.at[2, "ERSDA"] == "20240315"


def test_already_clean_dates_are_not_logged_as_changes(make_df, log):
    df = make_df([{"ERSDA": "2024-03-15"}])
    standardise_dates(df, CFG, log)
    assert not log.changes


def test_parse_date_returns_none_when_nothing_fits():
    assert parse_date("15 March 2024", FORMATS) is None
    assert parse_date("15.03.2024", FORMATS) == date(2024, 3, 15)
