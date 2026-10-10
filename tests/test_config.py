import copy

import pytest

from sap_cleaner.config import ConfigError, load_config, load_reference, validate_config


@pytest.mark.parametrize("data_type", ["material", "vendor"])
def test_built_in_configs_load(data_type):
    config = load_config(data_type)
    assert config["data_type"] == data_type
    assert config["rules"]


def test_reference_lists_are_text_not_yaml_booleans():
    # Unquoted, YAML would turn NO (Norway) into False.
    reference = load_reference()
    assert "NO" in reference["countries"]["valid"]
    assert "NA" in reference["countries"]["valid"]
    assert reference["units_of_measure"]["aliases"]["PCS"] == "PC"


def test_unknown_data_type():
    with pytest.raises(ConfigError, match="unknown data type"):
        load_config("customer")


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config("material", tmp_path / "nope.yaml")


def test_config_for_the_wrong_data_type(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("data_type: vendor\ncolumns: [LIFNR]\nrules: {}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="is for 'vendor' data"):
        load_config("material", path)


def test_invalid_yaml(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("columns: [A\nrules: {", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config("material", path)


@pytest.fixture
def config():
    return copy.deepcopy(load_config("vendor"))


def test_unknown_rule_name(config):
    config["rules"]["trimm"] = {}
    with pytest.raises(ConfigError, match="unknown rule 'trimm'"):
        validate_config(config)


def test_unknown_key_inside_a_rule(config):
    config["rules"]["uppercase"]["colums"] = ["LAND1"]
    with pytest.raises(ConfigError, match="unknown keys"):
        validate_config(config)


def test_rule_missing_a_required_key(config):
    del config["rules"]["dates"]["output_format"]
    with pytest.raises(ConfigError, match="is missing"):
        validate_config(config)


def test_rule_using_a_column_not_declared(config):
    config["rules"]["uppercase"]["columns"].append("LAND2")
    with pytest.raises(ConfigError, match="'LAND2', which is not in `columns`"):
        validate_config(config)


def test_fill_value_must_be_a_quoted_string(config):
    # Unquoted 0001 arrives from YAML as the number 1 and would lose its zeros.
    config["rules"]["mandatory"]["fields"]["ZTERM"]["value"] = 1
    with pytest.raises(ConfigError, match="quoted string value"):
        validate_config(config)


def test_bad_mandatory_action(config):
    config["rules"]["mandatory"]["fields"]["NAME1"] = {"action": "drop"}
    with pytest.raises(ConfigError, match="reject or action: fill"):
        validate_config(config)


@pytest.mark.parametrize("threshold", [0, 1.5, "high"])
def test_bad_near_duplicate_threshold(config, threshold):
    config["rules"]["near_duplicates"]["threshold"] = threshold
    with pytest.raises(ConfigError, match="threshold"):
        validate_config(config)


def test_bad_zero_pad_width(config):
    config["rules"]["zero_pad"]["columns"]["LIFNR"] = "ten"
    with pytest.raises(ConfigError, match="positive whole number"):
        validate_config(config)
