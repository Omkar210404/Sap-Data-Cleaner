const DATA = JSON.parse(document.getElementById('data').textContent);
const FILES = DATA.files;  // dataset key -> {file name: text}
const state = {ds: null, tab: 'overview'};
const all = (selector, root = document) => [...root.querySelectorAll(selector)];
const byId = id => document.getElementById(id);
const datasets = () => all('.ds');

// ---- which file and which tab are showing ----
function apply() {
  const list = datasets();
  if (!list.some(el => el.dataset.ds === state.ds)) state.ds = list.length ? list[0].dataset.ds : null;
  const current = list.find(el => el.dataset.ds === state.ds);
  list.forEach(el => el.hidden = el !== current);
  byId('empty').hidden = list.length > 0;
  all('[data-tab]').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === state.tab));
  all('[data-view]').forEach(v => v.hidden = v.dataset.view !== state.tab);

  const switcher = byId('datasets');
  switcher.textContent = '';
  list.forEach(el => {
    const button = document.createElement('button');
    button.textContent = button.title = el.dataset.label;
    button.setAttribute('aria-pressed', el === current);
    button.onclick = () => { state.ds = el.dataset.ds; apply(); };
    switcher.append(button);
  });

  const badge = byId('badge');
  const sample = current && current.dataset.kind === 'sample';
  badge.className = 'badge' + (sample ? ' sample' : '');
  badge.textContent = !current ? '' : sample ? 'SYNTHETIC DATA · not real company data'
                                             : 'Your file · cleaned on this computer, not saved';
  history.replaceState(null, '', current ? '#' + state.ds + '/' + state.tab : '#');
}

function fromHash() {
  const [ds, tab] = location.hash.slice(1).split('/');
  if (datasets().some(el => el.dataset.ds === ds)) state.ds = ds;
  if (all('[data-tab]').some(b => b.dataset.tab === tab)) state.tab = tab;
  apply();
}

function download(name, text) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([text], {type: name.endsWith('.txt') ? 'text/plain' : 'text/csv'}));
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

// Files are added after load, so clicks are handled once here instead of per button.
document.addEventListener('click', event => {
  const el = event.target.closest('[data-tab],[data-filter],[data-download],[data-open-upload],#open-upload');
  if (!el) return;
  if (el.dataset.tab) { state.tab = el.dataset.tab; apply(); }
  else if (el.dataset.filter) {
    const view = el.closest('.view');
    view.querySelector('.tablewrap').dataset.show = el.dataset.filter;
    all('[data-filter]', view).forEach(b => b.setAttribute('aria-pressed', b === el));
  }
  else if (el.dataset.download) download(el.dataset.download, FILES[el.closest('.ds').dataset.ds][el.dataset.download]);
  else openUpload();
});

document.addEventListener('change', event => {
  const el = event.target;
  if (el.matches('[data-show-old]'))
    el.closest('.view').querySelector('.tablewrap').classList.toggle('show-old', el.checked);
  else if (el.matches('[data-rule-filter]'))
    all('tbody tr', el.closest('.view')).forEach(tr => tr.hidden = !!el.value && tr.dataset.rule !== el.value);
});

// ---- upload dialog ----
const dialog = byId('upload');
const fileInput = byId('file');
let dataType = 'material';

function setType(type) {
  dataType = type;
  all('#type button').forEach(b => b.setAttribute('aria-pressed', b.dataset.type === type));
  byId('needs').textContent = DATA.columns[type].join(', ');
}

function showError(message) {
  byId('upload-error').textContent = message ? message[0].toUpperCase() + message.slice(1) : '';
  byId('upload-error').hidden = !message;
}

function openUpload() {
  showError('');
  dialog.showModal();
}

// Guess the separator and data type from the header line, so most files need no settings.
async function fileChosen() {
  const file = fileInput.files[0];
  byId('drop').classList.toggle('chosen', !!file);
  byId('submit-upload').disabled = !file;
  byId('drop-title').textContent = file ? file.name : 'Choose a file or drop it here';
  byId('drop-sub').textContent = file ? (file.size / 1024).toFixed(1) + ' KB · click to choose another'
                                      : 'CSV, up to ' + DATA.maxBytes / 1048576 + ' MB';
  showError('');
  if (!file) return;
  const header = (await file.slice(0, 4096).text()).split(/\r?\n/)[0];
  const count = separator => header.split(separator).length - 1;
  byId('delimiter').value = [',', ';', '\t', '|'].sort((a, b) => count(b) - count(a))[0];
  if (/\bLIFNR\b/i.test(header)) setType('vendor');
  else if (/\bMATNR\b/i.test(header)) setType('material');
}

async function submitUpload(event) {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;
  if (file.size > DATA.maxBytes) return showError('The file is larger than ' + DATA.maxBytes / 1048576 + ' MB.');
  const button = byId('submit-upload');
  button.disabled = true;
  button.textContent = 'Cleaning…';
  try {
    const query = new URLSearchParams({type: dataType, delimiter: byId('delimiter').value,
                                       encoding: byId('encoding').value, name: file.name});
    const response = await fetch('/api/clean?' + query, {method: 'POST', body: file});
    const result = await response.json();
    if (!result.ok) return showError(result.error);
    datasets().filter(el => el.dataset.ds === result.key).forEach(el => el.remove());
    byId('empty').insertAdjacentHTML('beforebegin', result.html);
    FILES[result.key] = result.files;
    state.ds = result.key;
    state.tab = 'overview';
    apply();
    dialog.close();
    fileInput.value = '';
    fileChosen();
  } catch (error) {
    showError('Could not reach the cleaner. Is "python -m sap_cleaner serve" still running?');
  } finally {
    button.textContent = 'Clean file';
    button.disabled = !fileInput.files[0];
  }
}

all('#type button').forEach(b => b.onclick = () => setType(b.dataset.type));
fileInput.onchange = fileChosen;
byId('upload-form').onsubmit = submitUpload;
byId('cancel-upload').onclick = () => dialog.close();
const drop = byId('drop');
['dragenter', 'dragover'].forEach(type => drop.addEventListener(type, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach(type => drop.addEventListener(type, e => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => {
  if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; fileChosen(); }
});

byId('max-size').textContent = DATA.maxBytes / 1048576;
setType('material');
addEventListener('hashchange', fromHash);
fromHash();
