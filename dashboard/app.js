(() => {
  'use strict';

  const API_BASE = '';
  const HEALTH_URL = `${API_BASE}/health`;
  const STATUS_URL = `${API_BASE}/status`;
  const FILES_URL = `${API_BASE}/files`;
  const LOGS_URL = `${API_BASE}/logs`;
  const CHANGES_URL = `${API_BASE}/sync/changes`;

  const LS_KEY = 'm10_api_key';

  const els = {
    apiKeyInput: document.getElementById('api-key-input'),
    saveKeyBtn: document.getElementById('save-key-btn'),
    authStatus: document.getElementById('auth-status'),
    mainContent: document.getElementById('main-content'),
    authBanner: document.getElementById('auth-banner'),
    errorBanner: document.getElementById('error-banner'),
    healthStatus: document.getElementById('health-status'),
    fileCount: document.getElementById('file-count'),
    deletedCount: document.getElementById('deleted-count'),
    conflictCount: document.getElementById('conflict-count'),
    logCount: document.getElementById('log-count'),
    changeCount: document.getElementById('change-count'),
    lastOperation: document.getElementById('last-operation'),
    adapterStatus: document.getElementById('adapter-status'),
    filesTableBody: document.querySelector('#files-table tbody'),
    logsTableBody: document.querySelector('#logs-table tbody'),
    changesTableBody: document.querySelector('#changes-table tbody'),
    refreshFilesBtn: document.getElementById('refresh-files-btn'),
    refreshLogsBtn: document.getElementById('refresh-logs-btn'),
    refreshChangesBtn: document.getElementById('refresh-changes-btn'),
    versionsModal: document.getElementById('versions-modal'),
    modalTitle: document.getElementById('modal-title'),
    modalClose: document.getElementById('modal-close'),
    versionsTableBody: document.querySelector('#versions-table tbody'),
  };

  let apiKey = '';

  function getApiKey() {
    try {
      return sessionStorage.getItem(LS_KEY) || '';
    } catch {
      return '';
    }
  }

  function setApiKey(value) {
    apiKey = value || '';
    if (apiKey) {
      try {
        sessionStorage.setItem(LS_KEY, apiKey);
      } catch {
        // ignore storage errors
      }
    } else {
      try {
        sessionStorage.removeItem(LS_KEY);
      } catch {
        // ignore storage errors
      }
    }
  }

  function authHeaders() {
    const headers = {
      Accept: 'application/json',
    };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    return headers;
  }

  function showError(message) {
    els.errorBanner.textContent = message;
    els.errorBanner.classList.remove('hidden');
    setTimeout(() => els.errorBanner.classList.add('hidden'), 5000);
  }

  function clearError() {
    els.errorBanner.classList.add('hidden');
    els.errorBanner.textContent = '';
  }

  async function fetchJson(url) {
    const response = await fetch(url, {
      method: 'GET',
      headers: authHeaders(),
    });

    if (response.status === 401) {
      handleUnauthorized();
      throw new Error('Unauthorized');
    }

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return response.json();
    }
    return response.blob();
  }

  function handleUnauthorized() {
    setApiKey('');
    els.apiKeyInput.value = '';
    els.authStatus.textContent = 'Invalid API key';
    els.mainContent.classList.add('hidden');
    els.authBanner.classList.remove('hidden');
  }

  async function loadStatus() {
    try {
      const [health, status] = await Promise.all([
        fetchJson(HEALTH_URL),
        fetchJson(STATUS_URL),
      ]);

      if (!health && !status) return;

      if (health) {
        els.healthStatus.textContent = health.status === 'ok' ? 'OK' : health.status;
      }

      if (status) {
        els.fileCount.textContent = String(status.file_count ?? 0);
        els.deletedCount.textContent = String(status.deleted_count ?? 0);
        els.conflictCount.textContent = String(status.conflict_count ?? 0);
        els.logCount.textContent = String(status.log_count ?? 0);
        els.changeCount.textContent = String(status.change_count ?? 0);
        els.lastOperation.textContent = status.last_operation_at || '--';
        const storage = status.storage_adapter === 's3' ? 'S3' : 'Memory';
        const meta = status.metadata_adapter === 'rds' ? 'RDS' : 'Memory';
        els.adapterStatus.textContent = `${storage} / ${meta}`;
      }
    } catch {
      // health/status failures are non-fatal for dashboard
    }
  }

  function formatBytes(bytes) {
    if (bytes == null || Number.isNaN(bytes)) return '--';
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / Math.pow(1024, i);
    return `${value.toFixed(value < 10 ? 1 : 0)} ${units[i]}`;
  }

  function statusBadge(status) {
    const map = {
      synced: 'badge-success',
      conflict: 'badge-danger',
      deleted: 'badge-muted',
    };
    const cls = map[status] || 'badge-muted';
    return `<span class="badge ${cls}">${escapeHtml(status)}</span>`;
  }

  function escapeHtml(value) {
    if (value == null) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function loadFiles() {
    try {
      const data = await fetchJson(FILES_URL);
      if (!data || !Array.isArray(data.files)) return;

      els.filesTableBody.innerHTML = '';
      const fragment = document.createDocumentFragment();
      data.files.forEach((file) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${escapeHtml(file.id)}</td>
          <td>${escapeHtml(file.filename)}</td>
          <td>${escapeHtml(file.relative_path)}</td>
          <td>${escapeHtml(file.current_version)}</td>
          <td>${statusBadge(file.status)}</td>
          <td>${escapeHtml(formatBytes(file.size))}</td>
          <td>${escapeHtml(file.updated_at)}</td>
        `;
        tr.addEventListener('click', () => openVersions(file.id, file.relative_path));
        fragment.appendChild(tr);
      });
      els.filesTableBody.appendChild(fragment);
    } catch {
      // non-fatal
    }
  }

  async function loadLogs() {
    try {
      const data = await fetchJson(LOGS_URL);
      if (!data || !Array.isArray(data.logs)) return;

      els.logsTableBody.innerHTML = '';
      const fragment = document.createDocumentFragment();
      const rows = data.logs.slice(-50).reverse();
      rows.forEach((log) => {
        const tr = document.createElement('tr');
        const badgeCls = log.status === 'SUCCESS' ? 'badge-success' : 'badge-danger';
        tr.innerHTML = `
          <td>${escapeHtml(log.id)}</td>
          <td>${escapeHtml(log.path)}</td>
          <td>${escapeHtml(log.operation)}</td>
          <td><span class="badge ${badgeCls}">${escapeHtml(log.status)}</span></td>
          <td>${escapeHtml(log.error_message || '')}</td>
          <td>${escapeHtml(log.timestamp)}</td>
        `;
        fragment.appendChild(tr);
      });
      els.logsTableBody.appendChild(fragment);
    } catch {
      // non-fatal
    }
  }

  async function loadChanges() {
    try {
      const data = await fetchJson(CHANGES_URL);
      if (!data || !Array.isArray(data.changes)) return;

      els.changesTableBody.innerHTML = '';
      const fragment = document.createDocumentFragment();
      const rows = data.changes.slice(-50).reverse();
      rows.forEach((change) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${escapeHtml(change.id)}</td>
          <td>${escapeHtml(change.path)}${change.dest_path ? ` → ${escapeHtml(change.dest_path)}` : ''}</td>
          <td>${escapeHtml(change.operation)}</td>
          <td>${escapeHtml(change.timestamp)}</td>
        `;
        fragment.appendChild(tr);
      });
      els.changesTableBody.appendChild(fragment);
    } catch {
      // non-fatal
    }
  }

  async function downloadVersion(fileId, versionNumber, filename) {
    try {
      const url = `${FILES_URL}/${encodeURIComponent(fileId)}/content?version=${encodeURIComponent(versionNumber)}`;
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          Accept: 'application/octet-stream',
          'X-API-Key': apiKey,
        },
      });

      if (response.status === 401) {
        handleUnauthorized();
        throw new Error('Unauthorized');
      }

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename || `file-v${versionNumber}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      if (err.message !== 'Unauthorized') {
        showError(`Download failed: ${err.message}`);
      }
    }
  }

  async function openVersions(fileId, relativePath) {
    els.modalTitle.textContent = `Version History: ${relativePath}`;
    els.versionsTableBody.innerHTML = '<tr><td colspan="7">Loading...</td></tr>';
    els.versionsModal.showModal();

    try {
      const data = await fetchJson(`${FILES_URL}/${encodeURIComponent(fileId)}/versions`);
      if (!data || !Array.isArray(data.versions) || data.versions.length === 0) {
        els.versionsTableBody.innerHTML = '<tr><td colspan="7">No versions found.</td></tr>';
        return;
      }

      els.versionsTableBody.innerHTML = '';
      const fragment = document.createDocumentFragment();
      const filename = relativePath.split('/').pop() || 'downloaded-file';
      data.versions.forEach((version) => {
        const tr = document.createElement('tr');
        const conflictBadge = version.is_conflict
          ? '<span class="badge badge-danger">conflict</span>'
          : '<span class="badge badge-muted">no</span>';
        const downloadBtn = document.createElement('button');
        downloadBtn.type = 'button';
        downloadBtn.className = 'btn-small';
        downloadBtn.textContent = 'Download';
        downloadBtn.addEventListener('click', (event) => {
          event.stopPropagation();
          downloadVersion(fileId, version.version_number, filename);
        });

        tr.innerHTML = `
          <td>${escapeHtml(version.version_number)}</td>
          <td>${escapeHtml(version.operation)}</td>
          <td>${escapeHtml(version.hash || '--')}</td>
          <td>${escapeHtml(formatBytes(version.size))}</td>
          <td>${escapeHtml(version.created_at)}</td>
          <td>${conflictBadge}</td>
          <td></td>
        `;
        tr.lastElementChild.appendChild(downloadBtn);
        fragment.appendChild(tr);
      });
      els.versionsTableBody.appendChild(fragment);
    } catch (err) {
      if (err.message !== 'Unauthorized') {
        els.versionsTableBody.innerHTML = '<tr><td colspan="7">Failed to load versions.</td></tr>';
      }
    }
  }

  async function refreshAll() {
    clearError();
    await Promise.all([loadStatus(), loadFiles(), loadLogs(), loadChanges()]);
  }

  function bindEvents() {
    els.saveKeyBtn.addEventListener('click', () => {
      const value = (els.apiKeyInput.value || '').trim();
      setApiKey(value);
      els.authStatus.textContent = value ? 'Saved' : 'Cleared';
      if (value) {
        els.authBanner.classList.add('hidden');
        els.mainContent.classList.remove('hidden');
        refreshAll();
      }
    });

    els.apiKeyInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        els.saveKeyBtn.click();
      }
    });

    els.refreshFilesBtn.addEventListener('click', () => loadFiles());
    els.refreshLogsBtn.addEventListener('click', () => loadLogs());
    els.refreshChangesBtn.addEventListener('click', () => loadChanges());

    els.modalClose.addEventListener('click', () => els.versionsModal.close());
    els.versionsModal.addEventListener('click', (event) => {
      if (event.target === els.versionsModal) {
        els.versionsModal.close();
      }
    });
  }

  function init() {
    bindEvents();
    apiKey = getApiKey();
    if (apiKey) {
      els.apiKeyInput.value = apiKey;
      els.authStatus.textContent = 'Loaded from session';
      refreshAll().then(() => {
        els.mainContent.classList.remove('hidden');
      });
    } else {
      els.authBanner.classList.remove('hidden');
      els.mainContent.classList.add('hidden');
    }
  }

  init();
})();
