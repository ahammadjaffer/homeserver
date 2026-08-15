/* NitroStream Drive — SPA File Manager */
'use strict';

// ─── STATE ─────────────────────────────────────────────────────────────────
const State = {
  currentFolderId: null,
  breadcrumbs: [{ id: null, name: 'My Drive' }],
  folders: [],
  files: [],
  viewMode: localStorage.getItem('ns_view') || 'grid',  // 'grid' | 'list'
  searchQuery: '',
  folderTree: [],
  uploadQueue: [],
  totalUploadBytes: 0,
  uploadedBytes: 0,
  uploadStartTime: 0,
  completedUploads: 0,
};

const MAX_CONCURRENT = 3;

// ─── UTILITIES ──────────────────────────────────────────────────────────────
function csrfToken() {
  return window.CSRF_TOKEN || document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

function formatBytes(b) {
  if (b === 0) return '0 B';
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  if (b < 1073741824) return (b / 1048576).toFixed(1) + ' MB';
  return (b / 1073741824).toFixed(2) + ' GB';
}

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function toast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

async function apiGet(url) {
  const r = await fetch(url, { headers: { 'X-CSRFToken': csrfToken() } });
  return r.json();
}

async function apiPost(url, body = {}) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: JSON.stringify(body),
  });
  return r.json();
}

// ─── FILE ICONS ─────────────────────────────────────────────────────────────
function fileIconSvg(iconType, cssClass = '') {
  const icons = {
    image: `<svg class="icon-image ${cssClass}" viewBox="0 0 24 24"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>`,
    video: `<svg class="icon-video ${cssClass}" viewBox="0 0 24 24"><path d="M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4z"/></svg>`,
    audio: `<svg class="icon-audio ${cssClass}" viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>`,
    pdf:   `<svg class="icon-pdf ${cssClass}" viewBox="0 0 24 24"><path d="M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8.5 7.5c0 .83-.67 1.5-1.5 1.5H9v2H7.5V7H10c.83 0 1.5.67 1.5 1.5v1zm5 2c0 .83-.67 1.5-1.5 1.5h-2.5V7H15c.83 0 1.5.67 1.5 1.5v3zm4-3H19v1h1.5V11H19v2h-1.5V7h3v1.5z"/></svg>`,
    file:  `<svg class="icon-file ${cssClass}" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>`,
    folder:`<svg viewBox="0 0 24 24" style="fill:var(--folder-color);width:52px;height:52px"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>`,
  };
  return icons[iconType] || icons.file;
}

// ─── SIDEBAR TOGGLE FOR MOBILE ──────────────────────────────────────────────
function toggleSidebar() {
  document.querySelector('.sidebar')?.classList.toggle('open');
  document.getElementById('sidebar-backdrop')?.classList.toggle('active');
}

function closeSidebar() {
  document.querySelector('.sidebar')?.classList.remove('open');
  document.getElementById('sidebar-backdrop')?.classList.remove('active');
}

// ─── LOAD FOLDER CONTENTS ───────────────────────────────────────────────────
async function loadFolder(folderId) {
  closeSidebar();

  const url = folderId == null
    ? '/api/folders/contents/'
    : `/api/folders/${folderId}/contents/`;

  const data = await apiGet(url);
  if (!data.success) { toast('Failed to load folder', 'error'); return; }

  State.currentFolderId = folderId;
  State.breadcrumbs = data.breadcrumbs;
  State.folders = data.folders;
  State.files = data.files;

  renderBreadcrumbs();
  renderContents();
  renderSidebarTree();
  updateToolbarCount();
}

// ─── RENDER BREADCRUMBS ──────────────────────────────────────────────────────
function renderBreadcrumbs() {
  const bar = document.getElementById('breadcrumb-bar');
  if (!bar) return;
  bar.innerHTML = State.breadcrumbs.map((bc, i) => {
    const isLast = i === State.breadcrumbs.length - 1;
    const sep = i > 0 ? `<span class="bc-sep">/</span>` : '';
    return `${sep}<span class="bc-item ${isLast ? 'active' : ''}" 
      onclick="${isLast ? '' : `loadFolder(${JSON.stringify(bc.id)})`}">${bc.name}</span>`;
  }).join('');
}

// ─── RENDER FILE GRID / LIST ─────────────────────────────────────────────────
function renderContents() {
  const area = document.getElementById('files-area');
  if (!area) return;

  const q = State.searchQuery.toLowerCase();
  const filteredFolders = State.folders.filter(f => f.name.toLowerCase().includes(q));
  const filteredFiles   = State.files.filter(f => f.filename.toLowerCase().includes(q));

  if (filteredFolders.length === 0 && filteredFiles.length === 0) {
    area.innerHTML = `<div class="empty-state">
      <svg viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
      <p>${State.searchQuery ? 'No results found.' : 'This folder is empty. Upload files or create a folder to get started.'}</p>
    </div>`;
    return;
  }

  let html = '';

  if (State.viewMode === 'grid') {
    if (filteredFolders.length) {
      html += `<div class="section-heading">Folders</div><div class="file-grid">`;
      filteredFolders.forEach(f => { html += renderFolderCard(f); });
      html += `</div>`;
    }
    if (filteredFiles.length) {
      html += `<div class="section-heading">Files</div><div class="file-grid">`;
      filteredFiles.forEach(f => { html += renderFileCard(f); });
      html += `</div>`;
    }
  } else {
    // List view — header row
    html += `<div class="section-heading" style="display:flex;gap:8px;padding:8px 12px;margin-top:8px;">
      <span style="flex:1">Name</span>
      <span style="width:80px;text-align:right">Size</span>
      <span style="width:120px;text-align:right">Modified</span>
      <span style="width:36px"></span>
    </div><div class="file-list">`;
    filteredFolders.forEach(f => { html += renderFolderListItem(f); });
    filteredFiles.forEach(f => { html += renderFileListItem(f); });
    html += `</div>`;
  }

  area.innerHTML = html;
}

function renderFolderCard(f) {
  return `<div class="file-card folder-card" 
      ondblclick="loadFolder(${f.id})"
      oncontextmenu="showContextMenu(event,'folder',${f.id},'${escAttr(f.name)}')" 
      onclick="handleCardClick(event,'folder',${f.id},'${escAttr(f.name)}')">
    <div class="card-thumb">${fileIconSvg('folder')}</div>
    <div class="card-info">
      <div class="card-name" title="${escAttr(f.name)}">${esc(f.name)}</div>
      <div class="card-meta">${f.file_count} item${f.file_count !== 1 ? 's' : ''}</div>
    </div>
    <button class="card-menu-btn" onclick="event.stopPropagation();showContextMenu(event,'folder',${f.id},'${escAttr(f.name)}')">
      <svg viewBox="0 0 24 24"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
    </button>
  </div>`;
}

function renderFileCard(f) {
  const ext = f.filename.split('.').pop().toUpperCase().slice(0, 5);
  const thumb = f.thumbnail_url
    ? `<img src="${f.thumbnail_url}" alt="${escAttr(f.filename)}" loading="lazy">`
    : `<div class="file-icon-wrap">${fileIconSvg(f.icon_type)}<span>${ext}</span></div>`;

  return `<div class="file-card"
      onclick="handleFileClick(event,${f.id},'${escAttr(f.filename)}','${escAttr(f.mime_type)}','${escAttr(f.stream_url)}')"
      oncontextmenu="showContextMenu(event,'file',${f.id},'${escAttr(f.filename)}')">
    <div class="card-thumb">
      ${thumb}
      <span class="type-badge">${ext}</span>
    </div>
    <div class="card-info">
      <div class="card-name" title="${escAttr(f.filename)}">${esc(f.filename)}</div>
      <div class="card-meta">${formatBytes(f.file_size)}</div>
    </div>
    <button class="card-menu-btn" onclick="event.stopPropagation();showContextMenu(event,'file',${f.id},'${escAttr(f.filename)}')">
      <svg viewBox="0 0 24 24"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
    </button>
  </div>`;
}

function renderFolderListItem(f) {
  return `<div class="list-item" ondblclick="loadFolder(${f.id})"
      oncontextmenu="showContextMenu(event,'folder',${f.id},'${escAttr(f.name)}')">
    <div class="list-icon">${fileIconSvg('folder','').replace('width:52px;height:52px','').replace('52px','22px')}</div>
    <div class="list-name">${esc(f.name)}</div>
    <div class="list-size">${f.file_count} items</div>
    <div class="list-date">${formatDate(f.created_at)}</div>
    <div class="list-actions">
      <button class="list-menu-btn" onclick="event.stopPropagation();showContextMenu(event,'folder',${f.id},'${escAttr(f.name)}')">
        <svg viewBox="0 0 24 24"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
      </button>
    </div>
  </div>`;
}

function renderFileListItem(f) {
  return `<div class="list-item"
      onclick="handleFileClick(event,${f.id},'${escAttr(f.filename)}','${escAttr(f.mime_type)}','${escAttr(f.stream_url)}')"
      oncontextmenu="showContextMenu(event,'file',${f.id},'${escAttr(f.filename)}')">
    <div class="list-icon">${fileIconSvg(f.icon_type)}</div>
    <div class="list-name">${esc(f.filename)}</div>
    <div class="list-size">${formatBytes(f.file_size)}</div>
    <div class="list-date">${formatDate(f.created_at)}</div>
    <div class="list-actions">
      <button class="list-menu-btn" onclick="event.stopPropagation();showContextMenu(event,'file',${f.id},'${escAttr(f.filename)}')">
        <svg viewBox="0 0 24 24"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
      </button>
    </div>
  </div>`;
}

function updateToolbarCount() {
  const el = document.getElementById('toolbar-count');
  if (el) el.textContent = `${State.folders.length} folder${State.folders.length !== 1 ? 's' : ''}, ${State.files.length} file${State.files.length !== 1 ? 's' : ''}`;
}

// ─── SIDEBAR FOLDER TREE ─────────────────────────────────────────────────────
async function loadSidebarTree() {
  const data = await apiGet('/api/folders/tree/');
  if (data.success) { State.folderTree = data.tree; renderSidebarTree(); }
}

function renderSidebarTree() {
  const el = document.getElementById('sidebar-tree');
  if (!el) return;
  const html = buildTreeHtml(State.folderTree, 0);
  el.innerHTML = html || `<div style="padding:8px 22px;font-size:0.78rem;color:var(--text-muted)">No folders yet</div>`;
}

function buildTreeHtml(nodes, depth) {
  return nodes.map(f => {
    const active = State.currentFolderId === f.id ? 'active' : '';
    const sub = (f.subfolders && f.subfolders.length)
      ? `<div class="tree-sub">${buildTreeHtml(f.subfolders, depth + 1)}</div>` : '';
    return `<div class="tree-item ${active}" style="padding-left:${10 + depth*10}px"
        onclick="loadFolder(${f.id})">
      <svg viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
      <span class="tree-item-name">${esc(f.name)}</span>
      <span class="tree-item-count">${f.file_count}</span>
    </div>${sub}`;
  }).join('');
}

// ─── CARD CLICK HANDLING ─────────────────────────────────────────────────────
function handleCardClick(event, type, id, name) {
  if (type === 'folder') {
    // single click selects, double-click navigates (handled by ondblclick)
  }
}

function handleFileClick(event, id, filename, mimeType, streamUrl) {
  if (mimeType && mimeType.startsWith('image/')) {
    openImageLightbox(streamUrl, filename);
  } else if (mimeType && mimeType.startsWith('video/')) {
    openVideoLightbox(streamUrl, filename);
  } else {
    window.open(streamUrl, '_blank');
  }
}

// ─── CONTEXT MENU ────────────────────────────────────────────────────────────
let _ctx = { type: null, id: null, name: null };

function showContextMenu(event, type, id, name) {
  event.preventDefault();
  event.stopPropagation();
  _ctx = { type, id, name };

  const menu = document.getElementById('context-menu');
  if (!menu) return;

  // Build items
  let items = '';
  if (type === 'folder') {
    items = `
      <div class="ctx-item" onclick="ctxOpen()">
        <svg viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>Open
      </div>
      <div class="ctx-item" onclick="ctxShare()">
        <svg viewBox="0 0 24 24"><path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92 1.61 0 2.92-1.31 2.92-2.92s-1.31-2.92-2.92-2.92z"/></svg>Share / Link
      </div>
      <div class="ctx-item" onclick="ctxRenameFolder()">
        <svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>Rename
      </div>
      <div class="ctx-divider"></div>
      <div class="ctx-item danger" onclick="ctxDeleteFolder()">
        <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>Delete
      </div>`;
  } else {
    items = `
      <div class="ctx-item" onclick="ctxOpenFile()">
        <svg viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zm0 12.5c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>Open / Preview
      </div>
      <div class="ctx-item" onclick="ctxShare()">
        <svg viewBox="0 0 24 24"><path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92 1.61 0 2.92-1.31 2.92-2.92s-1.31-2.92-2.92-2.92z"/></svg>Share / Link
      </div>
      <div class="ctx-item" onclick="ctxDownloadFile()">
        <svg viewBox="0 0 24 24"><path d="M12 16l-5-5h3V4h4v7h3l-5 5zm9 4H3v-2h18v2z"/></svg>Download
      </div>
      <div class="ctx-item" onclick="ctxRenameFile()">
        <svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>Rename
      </div>
      <div class="ctx-item" onclick="ctxMoveFile()">
        <svg viewBox="0 0 24 24"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z"/></svg>Move to…
      </div>
      <div class="ctx-divider"></div>
      <div class="ctx-item danger" onclick="ctxDeleteFile()">
        <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>Delete
      </div>`;
  }

  menu.innerHTML = items;
  menu.classList.add('open');

  // Position
  const x = Math.min(event.clientX, window.innerWidth - 200);
  const y = Math.min(event.clientY, window.innerHeight - 240);
  menu.style.left = x + 'px';
  menu.style.top  = y + 'px';
}

function hideContextMenu() {
  const menu = document.getElementById('context-menu');
  if (menu) menu.classList.remove('open');
}

// Context menu actions
function ctxOpen()        { loadFolder(_ctx.id); hideContextMenu(); }
function ctxOpenFile()    {
  const file = State.files.find(f => f.id === _ctx.id);
  if (file) handleFileClick(null, file.id, file.filename, file.mime_type, file.stream_url);
  hideContextMenu();
}
function ctxDownloadFile() {
  const file = State.files.find(f => f.id === _ctx.id);
  if (file) {
    const a = document.createElement('a');
    a.href = file.stream_url; a.download = file.filename; a.click();
  }
  hideContextMenu();
}

function ctxShare() {
  hideContextMenu();
  openShareModal(_ctx.type, _ctx.id, _ctx.name);
}

function ctxRenameFolder() {
  hideContextMenu();
  showModal('rename-modal');
  const inp = document.getElementById('rename-input');
  if (inp) { inp.value = _ctx.name; inp.focus(); inp.select(); }
  document.getElementById('rename-confirm').onclick = async () => {
    const newName = document.getElementById('rename-input').value.trim();
    if (!newName) return;
    const data = await apiPost(`/api/folders/${_ctx.id}/rename/`, { name: newName });
    hideModal('rename-modal');
    if (data.success) { toast('Folder renamed'); await loadFolder(State.currentFolderId); await loadSidebarTree(); }
    else toast(data.error || 'Rename failed', 'error');
  };
}

function ctxRenameFile() {
  hideContextMenu();
  showModal('rename-modal');
  const inp = document.getElementById('rename-input');
  if (inp) { inp.value = _ctx.name; inp.focus(); inp.select(); }
  document.getElementById('rename-confirm').onclick = async () => {
    const newName = document.getElementById('rename-input').value.trim();
    if (!newName) return;
    const data = await apiPost(`/api/files/${_ctx.id}/rename/`, { filename: newName });
    hideModal('rename-modal');
    if (data.success) { toast('File renamed'); await loadFolder(State.currentFolderId); }
    else toast(data.error || 'Rename failed', 'error');
  };
}

async function ctxDeleteFolder() {
  hideContextMenu();
  if (!confirm(`Delete folder "${_ctx.name}" and all its contents? This cannot be undone.`)) return;
  const data = await apiPost(`/api/folders/${_ctx.id}/delete/`);
  if (data.success) { toast('Folder deleted'); await loadFolder(State.currentFolderId); await loadSidebarTree(); }
  else toast(data.error || 'Delete failed', 'error');
}

async function ctxDeleteFile() {
  hideContextMenu();
  if (!confirm(`Delete "${_ctx.name}"? This cannot be undone.`)) return;
  const data = await apiPost(`/api/files/${_ctx.id}/delete/`);
  if (data.success) { toast('File deleted'); await loadFolder(State.currentFolderId); updateQuota(); }
  else toast(data.error || 'Delete failed', 'error');
}

function ctxMoveFile() {
  hideContextMenu();
  showMoveModal(_ctx.id, _ctx.name);
}

// ─── MOVE MODAL ──────────────────────────────────────────────────────────────
let _moveSelectedFolderId = null;

function showMoveModal(fileId, fileName) {
  _moveSelectedFolderId = null;
  const list = document.getElementById('folder-picker-list');
  if (!list) return;

  // Flatten folder tree for picking
  const all = [];
  const flatten = (nodes, depth) => nodes.forEach(f => {
    all.push({ id: f.id, name: f.name, depth });
    if (f.subfolders && f.subfolders.length) flatten(f.subfolders, depth + 1);
  });
  // Root option
  all.push({ id: null, name: 'My Drive (root)', depth: 0 });
  flatten(State.folderTree, 0);

  list.innerHTML = all.map(f => `
    <div class="folder-pick-item" onclick="selectMoveTarget(this, ${JSON.stringify(f.id)})" style="padding-left:${14 + (f.depth||0)*12}px">
      <svg viewBox="0 0 24 24" style="width:15px;height:15px;fill:var(--folder-color);flex-shrink:0"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
      ${esc(f.name)}
    </div>
  `).join('');

  showModal('move-modal');

  document.getElementById('move-confirm').onclick = async () => {
    const data = await apiPost(`/api/files/${fileId}/move/`, { folder_id: _moveSelectedFolderId });
    hideModal('move-modal');
    if (data.success) { toast('File moved'); await loadFolder(State.currentFolderId); await loadSidebarTree(); }
    else toast(data.error || 'Move failed', 'error');
  };
}

function selectMoveTarget(el, folderId) {
  document.querySelectorAll('.folder-pick-item').forEach(i => i.classList.remove('selected'));
  el.classList.add('selected');
  _moveSelectedFolderId = folderId;
}

// ─── NEW FOLDER ──────────────────────────────────────────────────────────────
function createFolderPrompt() {
  showModal('rename-modal');
  const inp = document.getElementById('rename-input');
  const title = document.getElementById('rename-modal-title');
  if (title) title.textContent = 'New Folder';
  if (inp) { inp.value = 'Untitled Folder'; inp.focus(); inp.select(); }
  document.getElementById('rename-confirm').onclick = async () => {
    const name = document.getElementById('rename-input').value.trim();
    if (!name) return;
    const data = await apiPost('/api/folders/create/', { name, parent_id: State.currentFolderId });
    hideModal('rename-modal');
    if (title) title.textContent = 'Rename';
    if (data.success) { toast('Folder created'); await loadFolder(State.currentFolderId); await loadSidebarTree(); }
    else toast(data.error || 'Failed to create folder', 'error');
  };
}

// ─── MODAL HELPERS ───────────────────────────────────────────────────────────
function showModal(id) { document.getElementById(id)?.classList.add('active'); }
function hideModal(id) { document.getElementById(id)?.classList.remove('active'); }

// ─── UPLOAD ──────────────────────────────────────────────────────────────────
function openUploadPanel() {
  document.getElementById('upload-panel').classList.add('open');
}
function closeUploadPanel() {
  document.getElementById('upload-panel').classList.remove('open');
}

function triggerFileInput() {
  document.getElementById('file-input').click();
}

function onFilesSelected(files) {
  if (!files || files.length === 0) return;
  openUploadPanel();

  const quotaBytes = (window.USER_STORAGE_QUOTA_MB || 5000) * 1048576;
  const usedBytes  = window.USER_USED_BYTES || 0;
  const totalNew   = Array.from(files).reduce((a, f) => a + f.size, 0);

  if (totalNew > quotaBytes - usedBytes) {
    toast(`Not enough storage. Needs ${formatBytes(totalNew)}, available ${formatBytes(quotaBytes - usedBytes)}.`, 'error');
    return;
  }

  State.uploadQueue = Array.from(files).map((file, idx) => ({
    id: idx, file, status: 'pending', uploadedBytes: 0
  }));
  State.totalUploadBytes = totalNew;
  State.uploadedBytes = 0;
  State.completedUploads = 0;
  State.uploadStartTime = Date.now();

  renderQueue();
  document.getElementById('upload-progress-section').style.display = 'block';
  processUploads();
}

function renderQueue() {
  const el = document.getElementById('upload-queue');
  if (!el) return;
  el.innerHTML = State.uploadQueue.map(item => `
    <div class="queue-item">
      <span class="queue-fname">${esc(item.file.name)}</span>
      <span class="queue-badge badge-pending" id="ubadge-${item.id}">Pending</span>
    </div>
  `).join('');
}

function setBadge(id, text, cls) {
  const el = document.getElementById(`ubadge-${id}`);
  if (el) { el.textContent = text; el.className = `queue-badge ${cls}`; }
}

function processUploads() {
  const active  = State.uploadQueue.filter(i => i.status === 'uploading').length;
  const pending = State.uploadQueue.filter(i => i.status === 'pending');
  if (active < MAX_CONCURRENT && pending.length) {
    uploadFile(pending[0]);
    processUploads();
  }
}

function uploadFile(item) {
  item.status = 'uploading';
  setBadge(item.id, 'Uploading…', 'badge-uploading');

  const fd = new FormData();
  fd.append('file', item.file);
  if (State.currentFolderId != null) fd.append('folder_id', State.currentFolderId);

  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/files/upload/', true);
  xhr.setRequestHeader('X-CSRFToken', csrfToken());

  let prev = 0;
  xhr.upload.onprogress = e => {
    if (e.lengthComputable) {
      State.uploadedBytes += e.loaded - prev;
      prev = e.loaded;
      updateUploadProgress();
    }
  };

  xhr.onload = async () => {
    State.completedUploads++;
    if (xhr.status === 200 || xhr.status === 201) {
      const res = JSON.parse(xhr.responseText);
      if (res.success) {
        setBadge(item.id, 'Done', 'badge-done');
        item.status = 'done';
        // Update used bytes globally
        window.USER_USED_BYTES = (window.USER_USED_BYTES || 0) + item.file.size;
        updateQuota();
      } else {
        setBadge(item.id, 'Failed', 'badge-failed');
        item.status = 'failed';
        toast(`Upload failed: ${res.error || 'Unknown error'}`, 'error');
      }
    } else {
      setBadge(item.id, 'Failed', 'badge-failed');
      item.status = 'failed';
    }
    onUploadComplete();
  };

  xhr.onerror = () => {
    item.status = 'failed';
    setBadge(item.id, 'Failed', 'badge-failed');
    State.completedUploads++;
    onUploadComplete();
  };

  xhr.send(fd);
}

function updateUploadProgress() {
  const pct = Math.min(100, Math.round((State.uploadedBytes / State.totalUploadBytes) * 100));
  const fill = document.getElementById('upload-bar-fill');
  const pctEl = document.getElementById('upload-pct');
  const summEl = document.getElementById('upload-summary');
  if (fill) fill.style.width = pct + '%';
  if (pctEl) pctEl.textContent = pct + '%';
  if (summEl) summEl.textContent = `${State.completedUploads} / ${State.uploadQueue.length} files`;

  const elapsed = (Date.now() - State.uploadStartTime) / 1000;
  if (elapsed > 0) {
    const speed = (State.uploadedBytes / 1048576 / elapsed).toFixed(1);
    const rem = State.totalUploadBytes - State.uploadedBytes;
    const eta = Math.round(rem / (State.uploadedBytes / elapsed));
    const speedEl = document.getElementById('upload-speed');
    const etaEl   = document.getElementById('upload-eta');
    if (speedEl) speedEl.textContent = `${speed} MB/s`;
    if (etaEl && isFinite(eta)) etaEl.textContent = `ETA: ${eta}s`;
  }
}

async function onUploadComplete() {
  processUploads();
  if (State.completedUploads === State.uploadQueue.length) {
    const summEl = document.getElementById('upload-summary');
    if (summEl) summEl.textContent = `🎉 All ${State.uploadQueue.length} file(s) uploaded!`;
    await loadFolder(State.currentFolderId);
  }
}

// ─── QUOTA BAR ───────────────────────────────────────────────────────────────
function updateQuota() {
  const used  = window.USER_USED_BYTES || 0;
  const quota = (window.USER_STORAGE_QUOTA_MB || 5000) * 1048576;
  const pct   = Math.min(100, (used / quota) * 100).toFixed(1);
  const fill  = document.getElementById('sidebar-quota-fill');
  const label = document.getElementById('sidebar-quota-label');
  if (fill)  fill.style.width = pct + '%';
  if (label) label.textContent = `${formatBytes(used)} of ${formatBytes(quota)} used`;
}

// ─── LIGHTBOX ────────────────────────────────────────────────────────────────
function openImageLightbox(src, filename) {
  const lb = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  const vid = document.getElementById('lightbox-video');
  const dl  = document.getElementById('lightbox-dl');
  const cap = document.getElementById('lightbox-caption');
  if (!lb) return;
  if (vid) { vid.pause(); vid.src = ''; vid.style.display = 'none'; }
  img.src = src; img.style.display = 'block';
  if (cap) cap.textContent = filename;
  if (dl)  { dl.href = src; dl.download = filename; }
  lb.classList.add('active');
}

function openVideoLightbox(src, filename) {
  const lb = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  const vid = document.getElementById('lightbox-video');
  const dl  = document.getElementById('lightbox-dl');
  const cap = document.getElementById('lightbox-caption');
  if (!lb) return;
  if (img) { img.src = ''; img.style.display = 'none'; }
  vid.src = src; vid.style.display = 'block'; vid.play();
  if (cap) cap.textContent = filename;
  if (dl)  { dl.href = src; dl.download = filename; }
  lb.classList.add('active');
}

function closeLightbox() {
  const lb  = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  const vid = document.getElementById('lightbox-video');
  if (lb)  lb.classList.remove('active');
  if (img) { img.src = ''; img.style.display = 'none'; }
  if (vid) { vid.pause(); vid.src = ''; vid.style.display = 'none'; }
}

// ─── SHARE MODAL & GRANULAR ACCESS CONTROL ──────────────────────────────────
let _shareCtx = { type: null, id: null, name: '', mode: 'private', url: '', users: [] };
let _userSearchTimer = null;

async function openShareModal(type, id, name) {
  _shareCtx = { type, id, name, mode: 'private', url: '', users: [] };
  const titleEl = document.getElementById('share-modal-title');
  const descEl  = document.getElementById('share-modal-desc');
  if (titleEl) titleEl.textContent = `Share "${name}"`;
  if (descEl)  descEl.textContent  = `Manage access settings for ${type === 'folder' ? 'folder' : 'file'}.`;

  const searchInp = document.getElementById('share-user-search');
  if (searchInp) searchInp.value = '';
  hideUserAutocomplete();

  showModal('share-modal');

  // Fetch current status from backend
  const data = await apiGet(`/api/shares/status/?type=${type}&id=${id}`);
  if (data.success) {
    _shareCtx.mode  = data.share_mode || (data.is_shared ? 'link' : 'private');
    _shareCtx.url   = data.share_url;
    _shareCtx.users = data.shared_users || [];
    renderShareModalUI();
  } else {
    toast(data.error || 'Failed to fetch share status', 'error');
  }
}

function selectShareMode(mode) {
  _shareCtx.mode = mode;
  renderShareModalUI();
}

function renderShareModalUI() {
  const mode = _shareCtx.mode;
  ['private', 'restricted', 'link'].forEach(m => {
    const card  = document.getElementById(`card-mode-${m}`);
    const radio = document.getElementById(`radio-mode-${m}`);
    if (card)  card.classList.toggle('selected', mode === m);
    if (radio) radio.checked = (mode === m);
  });

  const restrictedSec = document.getElementById('share-restricted-section');
  if (restrictedSec) restrictedSec.style.display = (mode === 'restricted') ? 'block' : 'none';

  const urlBox = document.getElementById('share-url-container');
  const urlInp = document.getElementById('share-url-input');
  if (mode === 'private') {
    if (urlBox) urlBox.style.display = 'none';
    if (urlInp) urlInp.value = '';
  } else {
    if (urlBox) urlBox.style.display = 'flex';
    if (urlInp) urlInp.value = _shareCtx.url;
  }

  renderUserChips();
}

function renderUserChips() {
  const container = document.getElementById('share-user-chips');
  if (!container) return;

  if (_shareCtx.users.length === 0) {
    container.innerHTML = `<div style="font-size:0.75rem; color:var(--text-muted);" id="no-users-label">No users added yet. Search and select accounts below.</div>`;
    return;
  }

  container.innerHTML = _shareCtx.users.map(u => `
    <div class="user-chip-badge">
      <span>${esc(u.username)}</span>
      <span class="chip-remove" onclick="removeUserFromShareList(${u.id})">&times;</span>
    </div>
  `).join('');
}

function onUserSearchInput(q) {
  clearTimeout(_userSearchTimer);
  q = q.trim();
  if (!q) {
    hideUserAutocomplete();
    return;
  }

  _userSearchTimer = setTimeout(async () => {
    const data = await apiGet(`/api/users/search/?q=${encodeURIComponent(q)}`);
    if (data.users && data.users.length > 0) {
      renderUserAutocomplete(data.users);
    } else {
      renderUserAutocomplete([]);
    }
  }, 250);
}

function renderUserAutocomplete(users) {
  const box = document.getElementById('share-user-results');
  if (!box) return;

  // Exclude users already added
  const existingIds = new Set(_shareCtx.users.map(u => u.id));
  const availableUsers = users.filter(u => !existingIds.has(u.id));

  if (availableUsers.length === 0) {
    box.innerHTML = `<div style="padding:8px 12px; font-size:0.8rem; color:var(--text-muted);">No matching accounts found.</div>`;
    box.style.display = 'block';
    return;
  }

  box.innerHTML = availableUsers.map(u => `
    <div class="user-autocomplete-item" onclick="addUserToShareList(${u.id}, '${escAttr(u.username)}')">
      <svg style="width:14px; height:14px; fill:currentColor;" viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
      <span>${esc(u.username)}</span>
    </div>
  `).join('');
  box.style.display = 'block';
}

function hideUserAutocomplete() {
  const box = document.getElementById('share-user-results');
  if (box) {
    box.style.display = 'none';
    box.innerHTML = '';
  }
}

function addUserToShareList(id, username) {
  if (!_shareCtx.users.some(u => u.id === id)) {
    _shareCtx.users.push({ id, username });
    renderUserChips();
  }
  const searchInp = document.getElementById('share-user-search');
  if (searchInp) searchInp.value = '';
  hideUserAutocomplete();
}

function removeUserFromShareList(userId) {
  _shareCtx.users = _shareCtx.users.filter(u => u.id !== userId);
  renderUserChips();
}

async function saveShareSettings() {
  const userIds = _shareCtx.users.map(u => u.id);
  const data = await apiPost('/api/shares/update/', {
    type: _shareCtx.type,
    id: _shareCtx.id,
    share_mode: _shareCtx.mode,
    user_ids: userIds
  });

  if (data.success) {
    _shareCtx.mode  = data.share_mode;
    _shareCtx.url   = data.share_url;
    _shareCtx.users = data.shared_users || [];
    hideModal('share-modal');
    if (_shareCtx.mode === 'private') {
      toast('Sharing disabled.');
    } else if (_shareCtx.mode === 'restricted') {
      toast(`Shared with ${data.shared_users.length} account(s)!`);
    } else {
      toast('Share link activated for all users!');
    }
  } else {
    toast(data.error || 'Failed to save share settings', 'error');
  }
}

// ─── VIEW TOGGLE ─────────────────────────────────────────────────────────────
function setView(mode) {
  State.viewMode = mode;
  localStorage.setItem('ns_view', mode);
  document.getElementById('btn-grid')?.classList.toggle('active', mode === 'grid');
  document.getElementById('btn-list')?.classList.toggle('active', mode === 'list');
  renderContents();
}

// ─── SEARCH ──────────────────────────────────────────────────────────────────
function onSearch(val) {
  State.searchQuery = val;
  renderContents();
}

// ─── DRAG AND DROP (whole window) ────────────────────────────────────────────
let _dragCounter = 0;
document.addEventListener('dragenter', e => {
  if (e.dataTransfer.types.includes('Files')) {
    _dragCounter++;
    document.getElementById('drop-overlay')?.classList.add('active');
  }
});
document.addEventListener('dragleave', () => {
  _dragCounter--;
  if (_dragCounter <= 0) { _dragCounter = 0; document.getElementById('drop-overlay')?.classList.remove('active'); }
});
document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', e => {
  e.preventDefault();
  _dragCounter = 0;
  document.getElementById('drop-overlay')?.classList.remove('active');
  if (e.dataTransfer.files.length) onFilesSelected(e.dataTransfer.files);
});

// ─── ESCAPE TO CLOSE ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeLightbox();
    hideModal('rename-modal');
    hideModal('move-modal');
    hideModal('share-modal');
    hideContextMenu();
  }
});

document.addEventListener('click', e => {
  if (!e.target.closest('.context-menu') && !e.target.closest('.card-menu-btn') && !e.target.closest('.list-menu-btn')) {
    hideContextMenu();
  }
});

// ─── HTML ESCAPE ─────────────────────────────────────────────────────────────
function esc(s)     { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(s) { return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

// ─── INIT ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Set initial view mode buttons
  document.getElementById('btn-grid')?.classList.toggle('active', State.viewMode === 'grid');
  document.getElementById('btn-list')?.classList.toggle('active', State.viewMode === 'list');

  // Load root folder and sidebar tree
  await Promise.all([loadFolder(null), loadSidebarTree()]);
  updateQuota();

  // File input handler
  const fileInput = document.getElementById('file-input');
  if (fileInput) fileInput.addEventListener('change', () => onFilesSelected(fileInput.files));

  // Drop zone inside upload panel
  const dropZone = document.getElementById('panel-drop-zone');
  if (dropZone) {
    dropZone.addEventListener('click', triggerFileInput);
    ['dragenter','dragover'].forEach(ev => dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add('dragover'); }));
    ['dragleave','drop'].forEach(ev => dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.remove('dragover'); }));
    dropZone.addEventListener('drop', e => { e.stopPropagation(); onFilesSelected(e.dataTransfer.files); });
  }

  // Modal cancel buttons
  document.querySelectorAll('[data-modal-close]').forEach(btn => {
    btn.addEventListener('click', () => hideModal(btn.dataset.modalClose));
  });

  // Lightbox click-outside to close
  document.getElementById('lightbox')?.addEventListener('click', e => {
    if (e.target.id === 'lightbox') closeLightbox();
  });
});
