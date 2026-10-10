"""Local web interface: python -m sap_cleaner serve

One page for trying the cleaner in a browser. It shows the runs on the
synthetic sample data and lets you upload a CSV, which is cleaned in memory by
the same pipeline the CLI uses, then offers the output files for download.

Nothing uploaded is written to disk. The server listens on 127.0.0.1 only and
has no login, so it is meant for your own machine, not for a network.
"""

from __future__ import annotations

import io
import json
import re
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .config import DATA_TYPES, ConfigError, load_config, load_reference
from .outputs import build_outputs
from .pipeline import InputError, clean, read_input
from .report import summarise

ASSETS = Path(__file__).parent / "webui"
SAMPLE_DIR = Path(__file__).parent.parent / "data" / "synthetic"
SAMPLES = (("materials", "material"), ("vendors", "vendor"))
DELIMITERS = (",", ";", "\t", "|")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_ROWS_SHOWN = 1000  # per table; the downloads always contain every row


def _show(value):
    """Cell text with blanks and stray spaces made visible."""
    text = str(value)
    if text == "":
        return "<i class='blank'>blank</i>"
    core = text.strip(" ")
    lead = len(text) - len(text.lstrip(" "))
    trail = len(text) - len(text.rstrip(" ")) if core else 0
    body = escape(core)
    while "  " in body:
        body = body.replace("  ", " <i class='ws'>·</i>", 1)

    def dots(count):
        return f"<i class='ws'>{chr(183) * count}</i>" if count else ""

    return f"{dots(lead)}{body}{dots(trail)}"


def _bars(counts, tone):
    if not counts:
        return "<p class='none'>None</p>"
    top = max(counts.values())
    return "".join(
        f"<div class='bar'><span class='lbl' title='{escape(str(label), quote=True)}'>{escape(str(label))}</span>"
        f"<span class='track'><span class='fill {tone}' style='width:{100 * count / top:.0f}%'></span></span>"
        f"<span class='num'>{count}</span></div>"
        for label, count in counts.items())


def _table(headers, body_rows):
    head = "".join(f"<th class='{'n' if header == 'Row' else ''}'>{escape(header)}</th>" for header in headers)
    return (f"<div class='tablewrap' data-show='all'><table><thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table></div>")


def _cap_note(total):
    if total <= MAX_ROWS_SHOWN:
        return ""
    return (f"<span class='hint cap'>Showing the first {MAX_ROWS_SHOWN:,} of {total:,} rows. "
            f"The downloads contain all of them.</span>")


def render_dataset(key, label, kind, data_type, source, result, files):
    """HTML for one cleaned file: the totals, the tabs and a view per tab."""
    summary = summarise(result)
    columns = list(source.columns)
    rejected_rows = set(result.rejected["SOURCE_ROW"])
    first_old = {}
    for change in result.changes.itertuples(index=False):
        first_old.setdefault((change.SOURCE_ROW, change.COLUMN), change.OLD_VALUE)

    rules = "".join(f"<span class='chip'>{i}. {escape(rule)}</span>" for i, rule in enumerate(result.rules_run, 1))
    overview = f"""
      <div class="cards">
        <div class="card"><h3>Changes by rule</h3><p class="sub">Fixes applied to rows that were kept</p>
          {_bars(summary['changes_by_rule'], 'ok')}</div>
        <div class="card"><h3>Rejected rows by reason</h3><p class="sub">A row with two problems counts under both</p>
          {_bars(summary['rejects_by_reason'], 'bad')}</div>
        <div class="card"><h3>Blanks filled with a default</h3><p class="sub">By field</p>
          {_bars(summary['fills_by_field'], 'ok')}
          <h3 class="gap">Rules run, in order</h3><div class="chips">{rules}</div></div>
      </div>"""

    rows = []
    for row, record in source.head(MAX_ROWS_SHOWN).iterrows():
        status = "rejected" if row in rejected_rows else "cleaned"
        cells = "".join(f"<td>{_show(record[c])}</td>" for c in columns)
        rows.append(f"<tr data-status='{status}' class='{'rej' if status == 'rejected' else ''}'>"
                    f"<td class='n'>{row}</td><td><span class='tag {status}'>{status}</span></td>{cells}</tr>")
    input_view = f"""
      <div class="toolbar"><div class="seg small">
          <button data-filter="all" aria-pressed="true">All {len(source)}</button>
          <button data-filter="cleaned" aria-pressed="false">Kept {len(result.cleaned)}</button>
          <button data-filter="rejected" aria-pressed="false">Rejected {len(result.rejected)}</button></div>
        <span class="hint"><i class="ws">·</i> marks a stray space &nbsp;&middot;&nbsp; the file as it arrived</span>
        {_cap_note(len(source))}</div>
      {_table(['Row', 'Outcome', *columns], rows)}"""

    rows = []
    for row, record in result.cleaned.head(MAX_ROWS_SHOWN).iterrows():
        cells = []
        for column in result.cleaned.columns:
            if (row, column) in first_old:
                cells.append(f"<td class='chg'><del>{_show(first_old[(row, column)])}</del>"
                             f"<span>{_show(record[column])}</span></td>")
            else:
                cells.append(f"<td>{_show(record[column])}</td>")
        rows.append(f"<tr><td class='n'>{row}</td>{''.join(cells)}</tr>")
    cleaned_view = f"""
      <div class="toolbar"><label class="check"><input type="checkbox" data-show-old> Show old values</label>
        <span class="hint"><span class="swatch"></span> green = changed by the cleaner</span>
        {_cap_note(len(result.cleaned))}</div>
      {_table(['Row', *result.cleaned.columns], rows)}"""

    rows = []
    for record in result.rejected.head(MAX_ROWS_SHOWN).to_dict("records"):
        reasons = "".join(f"<span class='reason'>{escape(r)}</span>" for r in record["REJECT_REASONS"].split("; "))
        cells = "".join(f"<td>{_show(record[c])}</td>" for c in columns)
        rows.append(f"<tr><td class='n'>{record['SOURCE_ROW']}</td><td class='why'>{reasons}</td>{cells}</tr>")
    rejected_view = f"""
      <div class="toolbar"><span class="hint">Rows set aside for a person to fix, with their original values untouched</span>
        {_cap_note(len(result.rejected))}</div>
      {_table(['Row', 'Why it was rejected', *columns], rows)}"""

    rows = []
    for change in result.changes.head(MAX_ROWS_SHOWN).itertuples(index=False):
        rows.append(f"<tr data-rule='{escape(change.RULE, quote=True)}'><td class='n'>{change.SOURCE_ROW}</td>"
                    f"<td>{escape(change.COLUMN)}</td><td class='old'>{_show(change.OLD_VALUE)}</td>"
                    f"<td class='arrow'>&rarr;</td><td class='new'>{_show(change.NEW_VALUE)}</td>"
                    f"<td><span class='chip'>{escape(change.RULE)}</span></td></tr>")
    options = "".join(f"<option value='{escape(rule, quote=True)}'>{escape(rule)} ({count})</option>"
                      for rule, count in summary["changes_by_rule"].items())
    changes_view = f"""
      <div class="toolbar"><label>Rule <select data-rule-filter>
          <option value="">All rules ({len(result.changes)})</option>{options}</select></label>
        <span class="hint">One line per change made to a kept row</span>{_cap_note(len(result.changes))}</div>
      {_table(['Row', 'Column', 'Old value', '', 'New value', 'Rule'], rows)}"""

    report_name = next(name for name in files if name.endswith("_report.txt"))
    report_view = f"""
      <div class="toolbar"><span class="hint">{escape(report_name)}, exactly as the tool writes it</span></div>
      <div class="tablewrap"><pre>{escape(files[report_name])}</pre></div>"""

    tabs = [("overview", "Overview", None, overview), ("input", "Input", len(source), input_view),
            ("cleaned", "Cleaned", len(result.cleaned), cleaned_view),
            ("rejected", "Rejected", len(result.rejected), rejected_view),
            ("changes", "Changes", len(result.changes), changes_view), ("report", "Report", None, report_view)]
    buttons = "".join(
        f"<button role='tab' data-tab='{tab}'>{name}{'' if count is None else f'<span class=count>{count}</span>'}</button>"
        for tab, name, count, _ in tabs)
    views = "".join(f"<div class='view' data-view='{tab}'>{html}</div>" for tab, _, _, html in tabs)
    downloads = "".join(
        f"<button data-download='{escape(name, quote=True)}'>{text}</button>"
        for name, text in zip(files, ("Cleaned CSV", "Rejected CSV", "Changes CSV", "Report")))
    return f"""
    <main class="ds" data-ds="{escape(key, quote=True)}" data-label="{escape(label, quote=True)}" data-kind="{kind}" hidden>
      <div class="stats">
        <div class="stat"><b>{summary['rows_read']}</b><span>rows read<small>{escape(label)} &middot; {data_type} rules</small></span></div>
        <div class="stat ok"><b>{summary['rows_cleaned']}</b><span>cleaned<small>passed every rule</small></span></div>
        <div class="stat bad"><b>{summary['rows_rejected']}</b><span>rejected<small>set aside with reasons</small></span></div>
        <div class="stat"><b>{summary['changes_total']}</b><span>changes<small>fixes to kept rows</small></span></div>
      </div>
      <div class="tabs" role="tablist">{buttons}
        <div class="downloads"><span>Download</span>{downloads}</div></div>
      {views}
    </main>"""


def clean_bytes(data, data_type, delimiter, encoding, filename, key, label, kind):
    """Clean CSV bytes with the built-in rules. Returns the page fragment and the output files."""
    if data_type not in DATA_TYPES:
        raise InputError(f"unknown data type '{data_type}'. Choose from: {', '.join(DATA_TYPES)}")
    if delimiter not in DELIMITERS:
        raise InputError("the separator must be a comma, semicolon, tab or pipe")
    source = read_input(io.BytesIO(data), delimiter, encoding, name=filename)
    result = clean(source, load_config(data_type), load_reference())
    stem = re.sub(r"[^\w.-]+", "_", Path(filename).stem).strip("_") or "upload"
    files = build_outputs(result, stem, delimiter, filename, data_type, f"built-in {data_type}.yaml")
    html = render_dataset(key, label, kind, data_type, source, result, files)
    return {"ok": True, "key": key, "html": html, "files": files}


def clean_upload(data, data_type, delimiter, encoding, filename):
    filename = Path(filename.replace("\\", "/")).name or "upload.csv"
    key = "file-" + (re.sub(r"[^A-Za-z0-9]+", "-", Path(filename).stem).strip("-") or "upload")
    return clean_bytes(data, data_type, delimiter, encoding, filename, key, filename, "upload")


def sample_runs():
    """The synthetic sample files, cleaned. Empty if the repository's data folder is absent."""
    runs = []
    for name, data_type in SAMPLES:
        path = SAMPLE_DIR / f"{name}.csv"
        if path.is_file():
            runs.append(clean_bytes(path.read_bytes(), data_type, ",", "utf-8-sig", path.name,
                                    f"sample-{name}", f"Sample {name}", "sample"))
    return runs


def render_page(runs):
    """The whole page: styles and script inlined, the given runs already rendered."""
    embedded = {
        "files": {run["key"]: run["files"] for run in runs},
        "columns": {data_type: load_config(data_type)["columns"] for data_type in DATA_TYPES},
        "maxBytes": MAX_UPLOAD_BYTES,
    }
    parts = {
        "/*STYLE*/": (ASSETS / "style.css").read_text(encoding="utf-8"),
        "<!--RUNS-->": "".join(run["html"] for run in runs),
        "/*DATA*/": json.dumps(embedded).replace("</", "<\\/"),
        "/*SCRIPT*/": (ASSETS / "app.js").read_text(encoding="utf-8"),
    }
    # One pass, so text inside an inserted part is never mistaken for a placeholder.
    pattern = "|".join(re.escape(placeholder) for placeholder in parts)
    return re.sub(pattern, lambda match: parts[match.group(0)], (ASSETS / "page.html").read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    server_version = "sap_cleaner"

    def _send(self, status, body, content_type):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json")

    def do_GET(self):
        if urlsplit(self.path).path in ("/", "/index.html"):
            self._send(200, self.server.page, "text/html")
        else:
            self._send(404, "Not found", "text/plain")

    def do_POST(self):
        parts = urlsplit(self.path)
        if parts.path != "/api/clean":
            return self._json(404, {"ok": False, "error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"ok": False, "error": "the request has no Content-Length"})
        if length > MAX_UPLOAD_BYTES:
            self.close_connection = True  # the body is not read, so the connection cannot be reused
            return self._json(413, {"ok": False, "error":
                                    f"the file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB"})
        data = self.rfile.read(length)
        query = {name: values[0] for name, values in parse_qs(parts.query, keep_blank_values=True).items()}
        try:
            payload = clean_upload(data, query.get("type", ""), query.get("delimiter", ","),
                                   query.get("encoding", "utf-8-sig"), query.get("name", "upload.csv"))
        except (InputError, ConfigError) as error:
            return self._json(400, {"ok": False, "error": str(error)})
        except Exception as error:  # keep the page usable whatever the file contains
            return self._json(500, {"ok": False, "error": f"unexpected error: {error}"})
        self._json(200, payload)

    def log_message(self, format, *args):
        pass  # quiet: uploaded file names should not end up in a console log


def make_server(port):
    """Create the server on 127.0.0.1. Port 0 picks a free port (used by the tests)."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.page = render_page(sample_runs())
    return server
