from sap_cleaner.rules.standardise import trim, uppercase, zero_pad

NULL_TOKENS = {"null_tokens": ["NULL", "N/A", "-"]}


def test_trim_strips_and_collapses_whitespace(make_df, log):
    df = make_df([{"MAKTX": "  HEX  BOLT   M8X20 ", "MEINS": "PC\t"}])
    trim(df, NULL_TOKENS, log)
    assert df.at[2, "MAKTX"] == "HEX BOLT M8X20"
    assert df.at[2, "MEINS"] == "PC"


def test_trim_removes_non_breaking_spaces(make_df, log):
    df = make_df([{"NAME1": " Tamsin Tools Inc "}])
    trim(df, NULL_TOKENS, log)
    assert df.at[2, "NAME1"] == "Tamsin Tools Inc"


def test_trim_turns_null_tokens_into_blanks(make_df, log):
    df = make_df([{"BRGEW": "N/A"}, {"BRGEW": "null"}, {"BRGEW": " - "}, {"BRGEW": "0.5"}])
    trim(df, NULL_TOKENS, log)
    assert df["BRGEW"].tolist() == ["", "", "", "0.5"]


def test_trim_keeps_na_because_it_is_namibia(make_df, log):
    df = make_df([{"LAND1": "NA"}])
    trim(df, NULL_TOKENS, log)
    assert df.at[2, "LAND1"] == "NA"


def test_trim_logs_only_cells_that_changed(make_df, log):
    df = make_df([{"MAKTX": " NUT M8", "MEINS": "PC"}, {"MAKTX": "WASHER M8", "MEINS": "PC"}])
    trim(df, NULL_TOKENS, log)
    assert log.changes == [{"row": 2, "column": "MAKTX", "old": " NUT M8", "new": "NUT M8", "rule": "trim"}]


def test_uppercase_only_touches_listed_columns(make_df, log):
    df = make_df([{"MTART": "roh", "MEINS": "pc", "NAME1": "Tamsin Tools Inc"}])
    uppercase(df, {"columns": ["MTART", "MEINS"]}, log)
    assert df.loc[2].tolist() == ["ROH", "PC", "Tamsin Tools Inc"]
    assert [change["column"] for change in log.changes] == ["MTART", "MEINS"]


PAD = {"columns": {"MATNR": 18}, "allowed_pattern": "[A-Z0-9-]+"}


def test_zero_pad_restores_leading_zeros(make_df, log):
    df = make_df([{"MATNR": "100023"}])
    zero_pad(df, PAD, log)
    assert df.at[2, "MATNR"] == "000000000000100023"
    assert log.changes[0]["rule"] == "zero_pad"


def test_zero_pad_leaves_correct_ids_alone(make_df, log):
    df = make_df([{"MATNR": "000000000000100023"}])
    zero_pad(df, PAD, log)
    assert df.at[2, "MATNR"] == "000000000000100023"
    assert log.changes == []


def test_zero_pad_uses_the_configured_width(make_df, log):
    df = make_df([{"LIFNR": "200014"}])
    zero_pad(df, {"columns": {"LIFNR": 10}}, log)
    assert df.at[2, "LIFNR"] == "0000200014"


def test_zero_pad_removes_spreadsheet_decimal(make_df, log):
    df = make_df([{"MATNR": "100007.0"}])
    zero_pad(df, PAD, log)
    assert df.at[2, "MATNR"] == "000000000000100007"


def test_zero_pad_does_not_pad_alphanumeric_ids(make_df, log):
    df = make_df([{"MATNR": "sp-4410"}])
    zero_pad(df, PAD, log)
    assert df.at[2, "MATNR"] == "SP-4410"


def test_zero_pad_trims_surplus_leading_zeros(make_df, log):
    df = make_df([{"MATNR": "00000000000000000100023"}])
    zero_pad(df, PAD, log)
    assert df.at[2, "MATNR"] == "000000000000100023"
    assert not log.rejects


def test_zero_pad_rejects_ids_that_are_too_long(make_df, log):
    df = make_df([{"MATNR": "1234567890123456789"}])
    zero_pad(df, PAD, log)
    assert log.reasons(2) == ["MATNR '1234567890123456789' is longer than 18 characters"]
    assert df.at[2, "MATNR"] == "1234567890123456789"


def test_zero_pad_rejects_scientific_notation(make_df, log):
    # What a spreadsheet does to a long numeric ID. The real number cannot be recovered.
    df = make_df([{"MATNR": "1.00045E+5"}])
    zero_pad(df, PAD, log)
    assert log.categories(2) == ["invalid MATNR"]
    assert "characters that are not allowed" in log.reasons(2)[0]


def test_zero_pad_skips_blank_ids(make_df, log):
    df = make_df([{"MATNR": ""}])
    zero_pad(df, PAD, log)
    assert df.at[2, "MATNR"] == ""
    assert not log.rejects
