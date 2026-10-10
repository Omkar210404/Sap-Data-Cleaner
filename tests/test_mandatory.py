from sap_cleaner.rules.mandatory import mandatory


def test_blank_field_with_reject_action_rejects_the_row(make_df, log):
    df = make_df([{"MAKTX": "", "MEINS": "PC"}, {"MAKTX": "HEX NUT M8", "MEINS": "PC"}])
    mandatory(df, {"fields": {"MAKTX": {"action": "reject"}}}, log)
    assert log.categories(2) == ["missing mandatory field MAKTX"]
    assert log.reasons(2) == ["MAKTX is blank"]
    assert not log.is_rejected(3)


def test_blank_field_with_fill_action_gets_the_default(make_df, log):
    df = make_df([{"ZTERM": ""}, {"ZTERM": "NT30"}])
    mandatory(df, {"fields": {"ZTERM": {"action": "fill", "value": "0001"}}}, log)
    assert df["ZTERM"].tolist() == ["0001", "NT30"]
    assert not log.rejects
    assert log.changes == [{"row": 2, "column": "ZTERM", "old": "", "new": "0001", "rule": "mandatory"}]


def test_conditional_fill_only_applies_when_the_other_field_has_a_value(make_df, log):
    df = make_df([{"BRGEW": "0.5", "GEWEI": ""}, {"BRGEW": "", "GEWEI": ""}, {"BRGEW": "2", "GEWEI": "G"}])
    mandatory(df, {"fields": {"GEWEI": {"action": "fill", "value": "KG", "when_present": "BRGEW"}}}, log)
    assert df["GEWEI"].tolist() == ["KG", "", "G"]
    assert len(log.changes) == 1


def test_a_row_collects_every_missing_field(make_df, log):
    df = make_df([{"NAME1": "", "ORT01": "", "LAND1": "IN"}])
    fields = {name: {"action": "reject"} for name in ("NAME1", "ORT01", "LAND1")}
    mandatory(df, {"fields": fields}, log)
    assert log.reasons(2) == ["NAME1 is blank", "ORT01 is blank"]


def test_complete_rows_are_untouched(make_df, log):
    df = make_df([{"NAME1": "Tamsin Tools Inc", "ZTERM": "NT30"}])
    mandatory(df, {"fields": {"NAME1": {"action": "reject"}, "ZTERM": {"action": "fill", "value": "0001"}}}, log)
    assert not log.rejects
    assert not log.changes
