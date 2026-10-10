import pytest

from sap_cleaner.config import load_reference
from sap_cleaner.rules.reference import country, unit_of_measure


@pytest.fixture(scope="module")
def reference():
    return load_reference()


@pytest.mark.parametrize("raw, expected", [
    ("PCS", "PC"), ("pcs", "PC"), ("ST", "PC"), ("EACH", "EA"), ("Nos", "EA"),
    ("KGS", "KG"), ("LTR", "L"), ("MTR", "M"), ("kg", "KG"), ("EA", "EA"),
])
def test_unit_aliases_map_to_the_standard_code(make_df, log, reference, raw, expected):
    df = make_df([{"MEINS": raw}])
    unit_of_measure(df, {"columns": ["MEINS"]}, reference, log)
    assert df.at[2, "MEINS"] == expected
    assert not log.rejects


def test_unknown_unit_is_rejected_and_left_untouched(make_df, log, reference):
    df = make_df([{"MEINS": "QQ"}])
    unit_of_measure(df, {"columns": ["MEINS"]}, reference, log)
    assert log.categories(2) == ["unknown unit of measure in MEINS"]
    assert log.reasons(2) == ["MEINS 'QQ' is not a known unit of measure"]
    assert df.at[2, "MEINS"] == "QQ"


def test_blank_unit_is_left_for_the_mandatory_rule(make_df, log, reference):
    df = make_df([{"MEINS": ""}])
    unit_of_measure(df, {"columns": ["MEINS"]}, reference, log)
    assert not log.rejects


def test_unit_rule_checks_every_listed_column(make_df, log, reference):
    df = make_df([{"MEINS": "PCS", "GEWEI": "KGS"}, {"MEINS": "EA", "GEWEI": "STONE"}])
    unit_of_measure(df, {"columns": ["MEINS", "GEWEI"]}, reference, log)
    assert df.loc[2].tolist() == ["PC", "KG"]
    assert log.categories(3) == ["unknown unit of measure in GEWEI"]


def test_unit_alias_is_logged_as_a_change(make_df, log, reference):
    df = make_df([{"MEINS": "PCS"}])
    unit_of_measure(df, {"columns": ["MEINS"]}, reference, log)
    assert log.changes == [{"row": 2, "column": "MEINS", "old": "PCS", "new": "PC", "rule": "unit_of_measure"}]


@pytest.mark.parametrize("raw, expected", [
    ("India", "IN"), ("IND", "IN"), ("Germany", "DE"), ("DEU", "DE"), ("USA", "US"),
    ("United States", "US"), ("UK", "GB"), ("in", "IN"), ("NA", "NA"), ("NO", "NO"),
])
def test_country_aliases_map_to_iso_codes(make_df, log, reference, raw, expected):
    df = make_df([{"LAND1": raw}])
    country(df, {"columns": ["LAND1"]}, reference, log)
    assert df.at[2, "LAND1"] == expected
    assert not log.rejects


@pytest.mark.parametrize("raw", ["ZZ", "Atlantis", "I N"])
def test_unknown_country_is_rejected(make_df, log, reference, raw):
    df = make_df([{"LAND1": raw}])
    country(df, {"columns": ["LAND1"]}, reference, log)
    assert log.categories(2) == ["unknown country code in LAND1"]
    assert log.reasons(2) == [f"LAND1 '{raw}' is not a known country code"]


def test_blank_country_is_left_for_the_mandatory_rule(make_df, log, reference):
    df = make_df([{"LAND1": ""}])
    country(df, {"columns": ["LAND1"]}, reference, log)
    assert not log.rejects
