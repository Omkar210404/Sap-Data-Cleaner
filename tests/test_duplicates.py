import pytest

from sap_cleaner.rules.duplicates import exact_duplicates, near_duplicates, normalise, similarity

LEGAL_FORMS = ["PVT", "PRIVATE", "LTD", "LIMITED", "INC", "GMBH"]


def vendor(lifnr, name, country="IN", city="Pune"):
    return {"LIFNR": lifnr, "NAME1": name, "ORT01": city, "LAND1": country}


def material(matnr, text, plant="1000", mtart="ROH"):
    return {"MATNR": matnr, "MAKTX": text, "MTART": mtart, "WERKS": plant}


# --- exact duplicates -------------------------------------------------------

def test_exact_duplicate_keeps_the_first_row(make_df, log):
    df = make_df([vendor("0000200014", "Tamsin Tools Inc"), vendor("0000200099", "Other Vendor"),
                  vendor("0000200014", "Tamsin Tools Inc")])
    exact_duplicates(df, {"key": ["LIFNR"]}, log)
    assert not log.is_rejected(2)
    assert log.categories(4) == ["exact duplicate"]
    assert log.reasons(4) == ["exact duplicate of row 2"]


def test_every_later_copy_points_at_the_first_row(make_df, log):
    df = make_df([vendor("0000200014", "Tamsin Tools Inc")] * 3)
    exact_duplicates(df, {"key": ["LIFNR"]}, log)
    assert log.reasons(3) == log.reasons(4) == ["exact duplicate of row 2"]


def test_exact_duplicate_ignores_letter_case_by_default(make_df, log):
    df = make_df([vendor("0000200014", "Tamsin Tools Inc"), vendor("0000200014", "TAMSIN TOOLS INC")])
    exact_duplicates(df, {"key": ["LIFNR"]}, log)
    assert log.categories(3) == ["exact duplicate"]


def test_case_difference_is_a_conflict_when_ignore_case_is_off(make_df, log):
    df = make_df([vendor("0000200014", "Tamsin Tools Inc"), vendor("0000200014", "TAMSIN TOOLS INC")])
    exact_duplicates(df, {"key": ["LIFNR"], "ignore_case": False}, log)
    assert log.categories(3) == ["key conflict"]


def test_same_key_with_different_data_is_a_key_conflict(make_df, log):
    df = make_df([vendor("0000200020", "Colles Aurelienne SAS", "FR", "Lyon"),
                  vendor("0000200020", "Colles Aurelienne SAS", "FR", "Marseille")])
    exact_duplicates(df, {"key": ["LIFNR"]}, log)
    assert log.categories(3) == ["key conflict"]
    assert log.reasons(3) == ["same LIFNR as row 2 but different ORT01"]


def test_same_material_in_two_plants_is_not_a_duplicate(make_df, log):
    df = make_df([material("000000000000100003", "HEX NUT M8", "1000"),
                  material("000000000000100003", "HEX NUT M8", "2000")])
    exact_duplicates(df, {"key": ["MATNR", "WERKS"]}, log)
    assert not log.rejects


def test_already_rejected_row_is_not_kept_as_the_original(make_df, log):
    df = make_df([vendor("0000200014", "Tamsin Tools Inc")] * 2)
    log.reject(2, "invalid date in ERDAT", "ERDAT 'TBD' is not a valid date")
    exact_duplicates(df, {"key": ["LIFNR"]}, log)
    assert not log.is_rejected(3)


# --- near-duplicates --------------------------------------------------------

VENDOR_RULE = {"column": "NAME1", "block_by": ["LAND1"], "distinct_on": ["LIFNR"],
               "threshold": 0.9, "ignore_tokens": LEGAL_FORMS}
MATERIAL_RULE = {"column": "MAKTX", "block_by": ["MTART"], "distinct_on": ["MATNR"], "threshold": 0.9}


def test_normalise_drops_case_punctuation_legal_forms_and_word_order():
    assert normalise("Zentrix Bearings Pvt. Ltd.", LEGAL_FORMS) == "bearings zentrix"
    assert normalise("Finch & Marlowe Packaging") == normalise("MARLOWE & FINCH PACKAGING")
    assert normalise("  ") == ""


def test_similarity_is_one_for_identical_text_and_lower_for_a_typo():
    assert similarity("bearings zentrix", "bearings zentrix") == 1.0
    assert 0.9 < similarity("industrial kavora supplies", "industrial kavora suplies") < 1.0


@pytest.mark.parametrize("variant", [
    "Zentrix Bearings Private Limited",   # different legal form
    "ZENTRIX BEARINGS PVT. LTD.",          # case and punctuation
    "Bearings Zentrix Pvt Ltd",            # word order
    "Zentrix Bearngs Pvt Ltd",             # typo
])
def test_near_duplicate_vendor_names_are_caught(make_df, log, variant):
    df = make_df([vendor("0000200001", "Zentrix Bearings Pvt Ltd"), vendor("0000200101", variant)])
    near_duplicates(df, VENDOR_RULE, log)
    assert not log.is_rejected(2)
    assert log.categories(3) == ["near-duplicate"]
    assert log.reasons(3)[0].startswith("near-duplicate of row 2 (NAME1 similarity ")


def test_the_reason_reports_the_similarity_score(make_df, log):
    df = make_df([vendor("0000200002", "Kavora Industrial Supplies"),
                  vendor("0000200102", "Kavora Industrial Suplies")])
    near_duplicates(df, VENDOR_RULE, log)
    expected = similarity(normalise("Kavora Industrial Supplies"), normalise("Kavora Industrial Suplies"))
    assert log.reasons(3) == [f"near-duplicate of row 2 (NAME1 similarity {expected:.2f})"]


def test_different_names_are_not_near_duplicates(make_df, log):
    df = make_df([vendor("0000200001", "Zentrix Bearings Pvt Ltd"),
                  vendor("0000200005", "Orbita Electricals Pvt Ltd")])
    near_duplicates(df, VENDOR_RULE, log)
    assert not log.rejects


def test_threshold_decides_what_counts(make_df, log):
    rows = [vendor("0000200002", "Kavora Industrial Supplies"), vendor("0000200102", "Kavora Industrial Suplies")]
    near_duplicates(make_df(rows), {**VENDOR_RULE, "threshold": 0.99}, log)
    assert not log.rejects
    near_duplicates(make_df(rows), {**VENDOR_RULE, "threshold": 0.9}, log)
    assert log.is_rejected(3)


def test_same_name_in_another_country_is_a_different_vendor(make_df, log):
    df = make_df([vendor("0000200003", "Sundara Steel Traders", "IN"),
                  vendor("0000200004", "Sundara Steel Traders", "AE")])
    near_duplicates(df, VENDOR_RULE, log)
    assert not log.rejects


def test_texts_with_different_numbers_are_never_near_duplicates(make_df, log):
    df = make_df([material("000000000000100001", "HEX BOLT M8X20 ZINC PLATED"),
                  material("000000000000100002", "HEX BOLT M8X25 ZINC PLATED")])
    near_duplicates(df, MATERIAL_RULE, log)
    assert not log.rejects


def test_near_duplicate_material_descriptions_are_caught(make_df, log):
    df = make_df([material("000000000000100008", "HYDRAULIC OIL ISO VG 46"),
                  material("000000000000100102", "HYDRALIC OIL ISO VG 46"),
                  material("000000000000100103", "OIL HYDRAULIC ISO VG 46")])
    near_duplicates(df, MATERIAL_RULE, log)
    assert log.reasons(3)[0].startswith("near-duplicate of row 2")
    assert log.reasons(4) == ["near-duplicate of row 2 (MAKTX similarity 1.00)"]


def test_same_material_number_in_two_plants_is_not_a_near_duplicate(make_df, log):
    df = make_df([material("000000000000100003", "HEX NUT M8", "1000"),
                  material("000000000000100003", "HEX NUT M8", "2000")])
    near_duplicates(df, MATERIAL_RULE, log)
    assert not log.rejects


def test_materials_of_another_type_are_not_compared(make_df, log):
    df = make_df([material("000000000000100008", "HYDRAULIC OIL ISO VG 46", mtart="HIBE"),
                  material("000000000000100102", "HYDRAULIC OIL ISO VG 46", mtart="ROH")])
    near_duplicates(df, MATERIAL_RULE, log)
    assert not log.rejects


def test_flag_action_keeps_the_row_and_records_a_note(make_df, log):
    df = make_df([vendor("0000200001", "Zentrix Bearings Pvt Ltd"),
                  vendor("0000200101", "Zentrix Bearings Private Limited")])
    near_duplicates(df, {**VENDOR_RULE, "action": "flag"}, log)
    assert not log.rejects
    assert log.flags == {3: "near-duplicate of row 2 (NAME1 similarity 1.00)"}


def test_rejected_rows_and_blank_texts_are_skipped(make_df, log):
    df = make_df([vendor("0000200001", "Zentrix Bearings Pvt Ltd"),
                  vendor("0000200101", "Zentrix Bearings Private Limited"),
                  vendor("0000200102", ""), vendor("0000200103", "")])
    log.reject(2, "missing mandatory field KTOKK", "KTOKK is blank")
    near_duplicates(df, VENDOR_RULE, log)
    assert [row for row in df.index if log.is_rejected(row)] == [2]
