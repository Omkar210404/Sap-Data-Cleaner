"""The local web page: a real server on a free port, driven over HTTP."""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

import pytest

from sap_cleaner import web

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "synthetic"
EXAMPLES = ROOT / "examples" / "output"


@pytest.fixture(scope="module")
def base_url():
    server = web.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(url):
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def post(base_url, data, **query):
    request = urllib.request.Request(f"{base_url}/api/clean?{urlencode(query)}", data=data, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def vendor_csv(*rows):
    header = "LIFNR,NAME1,ORT01,PSTLZ,LAND1,STCD1,KTOKK,ZTERM,WAERS,ERDAT"
    return "\n".join([header, *rows]).encode("utf-8")


def test_page_loads_with_the_sample_runs_and_the_upload_form(base_url):
    status, page = get(base_url + "/")
    assert status == 200
    assert 'data-ds="sample-materials"' in page and 'data-ds="sample-vendors"' in page
    assert 'id="upload-form"' in page
    assert "SYNTHETIC DATA" in page
    # Every placeholder in the template was filled.
    assert "/*STYLE*/" not in page and "/*SCRIPT*/" not in page and "<!--RUNS-->" not in page


def test_unknown_paths_are_404(base_url):
    assert get(base_url + "/secret.txt")[0] == 404
    assert post(base_url, b"x")[0] == 400  # right path, but no data type
    request = urllib.request.Request(base_url + "/api/other", data=b"x", method="POST")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 404


@pytest.mark.parametrize("name, data_type", [("materials", "material"), ("vendors", "vendor")])
def test_upload_gives_the_same_files_as_the_cli(base_url, name, data_type):
    data = (SAMPLES / f"{name}.csv").read_bytes()
    status, result = post(base_url, data, type=data_type, delimiter=",", encoding="utf-8-sig", name=f"{name}.csv")
    assert status == 200 and result["ok"]
    assert result["key"] == f"file-{name}"
    assert set(result["files"]) == {path.name for path in EXAMPLES.glob(f"{name}_*")}
    for kind in ("cleaned", "rejected", "changes"):
        expected = (EXAMPLES / f"{name}_{kind}.csv").read_text(encoding="utf-8")
        assert result["files"][f"{name}_{kind}.csv"] == expected, kind
    # The report differs only in how the input file is named.
    expected = (EXAMPLES / f"{name}_report.txt").read_text(encoding="utf-8")
    assert result["files"][f"{name}_report.txt"] == expected.replace(f"data/synthetic/{name}.csv", f"{name}.csv")


def test_upload_returns_a_page_section_for_the_file(base_url):
    data = (SAMPLES / "vendors.csv").read_bytes()
    _, result = post(base_url, data, type="vendor", name="my vendors (final).csv")
    assert result["key"] == "file-my-vendors-final"
    assert 'data-label="my vendors (final).csv"' in result["html"]
    assert 'data-kind="upload"' in result["html"]
    assert "near-duplicate of row 2" in result["html"]
    assert set(result["files"]) == {f"my_vendors_final_{suffix}" for suffix in
                                    ("cleaned.csv", "rejected.csv", "changes.csv", "report.txt")}


def test_semicolon_separated_upload(base_url):
    data = (SAMPLES / "vendors.csv").read_bytes().replace(b",", b";")
    status, result = post(base_url, data, type="vendor", delimiter=";", name="vendors.csv")
    assert status == 200
    expected = (EXAMPLES / "vendors_cleaned.csv").read_text(encoding="utf-8").replace(",", ";")
    assert result["files"]["vendors_cleaned.csv"] == expected


def test_file_of_the_wrong_type_is_a_readable_error(base_url):
    status, result = post(base_url, (SAMPLES / "vendors.csv").read_bytes(), type="material", name="vendors.csv")
    assert status == 400
    assert result == {"ok": False, "error": "input file is missing columns the rules need: "
                                            "MATNR, MAKTX, MTART, MATKL, MEINS, WERKS, BRGEW, GEWEI, ERSDA"}


@pytest.mark.parametrize("data, query, message", [
    (b"", {"type": "vendor", "name": "empty.csv"}, "input file is empty: empty.csv"),
    (b"a,b\n1,2\n", {"type": "customer"}, "unknown data type 'customer'"),
    (b"a,b\n1,2\n", {"type": "vendor", "delimiter": "ab"}, "separator must be"),
    (b"a,b\n1,2\n", {"type": "vendor", "encoding": "klingon"}, "unknown encoding: klingon"),
    ("LIFNR,NAME1\n1,Müller\n".encode("cp1252"), {"type": "vendor", "name": "v.csv"}, "could not read v.csv"),
])
def test_bad_uploads_are_rejected_with_a_message(base_url, data, query, message):
    status, result = post(base_url, data, **query)
    assert status == 400
    assert not result["ok"] and message in result["error"]


def test_upload_over_the_size_limit_is_refused(base_url, monkeypatch):
    monkeypatch.setattr(web, "MAX_UPLOAD_BYTES", 100)
    status, result = post(base_url, b"x" * 101, type="vendor")
    assert status == 413
    assert "larger than" in result["error"]


def test_uploaded_values_are_escaped_in_the_page(base_url):
    row = '200001,<script>alert(1)</script>,"<img src=x onerror=alert(2)>",411019,IN,SYN1,ZDOM,NT30,INR,2024-01-01'
    _, result = post(base_url, vendor_csv(row), type="vendor", name='<b onclick="x">.csv')
    assert result["ok"]
    assert "<script>" not in result["html"] and "<img" not in result["html"] and "<b onclick" not in result["html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result["html"]
    assert 'data-label="&lt;b onclick=&quot;x&quot;&gt;.csv"' in result["html"]
    # The downloadable file still holds the real value.
    assert "<script>alert(1)</script>" in result["files"]["b_onclick_x_cleaned.csv"]


def test_file_name_cannot_carry_a_path(base_url):
    _, result = post(base_url, vendor_csv(), type="vendor", name="..\\..\\secrets/../evil.csv")
    assert result["ok"]
    assert all(name.startswith("evil_") for name in result["files"])


def test_large_tables_are_capped_on_the_page_but_not_in_the_files(base_url, monkeypatch):
    monkeypatch.setattr(web, "MAX_ROWS_SHOWN", 5)
    rows = [f"{200000 + i},Vendor Number {i},Pune,411019,IN,SYN{i},ZDOM,NT30,INR,2024-01-01" for i in range(12)]
    _, result = post(base_url, vendor_csv(*rows), type="vendor", name="many.csv")
    assert "Showing the first 5 of 12 rows" in result["html"]
    assert result["html"].count("data-status=") == 5
    assert len(result["files"]["many_cleaned.csv"].splitlines()) == 13


def test_nothing_is_written_to_disk_by_an_upload(base_url, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    post(base_url, (SAMPLES / "vendors.csv").read_bytes(), type="vendor", name="vendors.csv")
    assert list(tmp_path.iterdir()) == []


def test_page_without_sample_data_starts_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "SAMPLE_DIR", tmp_path)
    page = web.render_page(web.sample_runs())
    assert 'class="ds"' not in page
    assert 'id="empty"' in page
