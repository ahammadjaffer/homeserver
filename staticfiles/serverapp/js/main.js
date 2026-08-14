/* NitroStream — Main Application JavaScript */

const MAX_CONCURRENT_UPLOADS = 3;

/* Retrieve CSRF Token from DOM or global variable */
function getCsrfToken() {
    if (window.CSRF_TOKEN) return window.CSRF_TOKEN;
    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    return csrfInput ? csrfInput.value : '';
}

/* Retrieve Upload AJAX URL from global variable or default endpoint */
function getUploadUrl() {
    return window.UPLOAD_AJAX_URL || '/upload-ajax/';
}

/* TOGGLE UPLOAD DRAWER */
function toggleUploadDrawer() {
    const wrapper = document.getElementById('upload-wrapper');
    if (!wrapper) return;
    wrapper.classList.toggle('open');
    if (wrapper.classList.contains('open')) {
        wrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

/* SCROLL TO SECTION */
function scrollToSection(id, btnElement) {
    if (btnElement) {
        document.querySelectorAll('.nav-link-btn').forEach(btn => btn.classList.remove('active'));
        btnElement.classList.add('active');
    }

    if (id === 'all') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
    }

    const target = document.getElementById(id);
    if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

/* UPDATE SELECTED FILE COUNT DISPLAY */
function updateSelectedCount() {
    const input = document.getElementById('file-input');
    const countSpan = document.getElementById('selected-count');
    if (!input || !countSpan) return;
    if (input.files.length > 0) {
        countSpan.textContent = `Selected: ${input.files.length} file(s)`;
    } else {
        countSpan.textContent = '';
    }
}

/* REAL-TIME CLIENT-SIDE SEARCH FUNCTION */
function filterFiles() {
    const searchInput = document.getElementById('search-input');
    if (!searchInput) return;
    const query = searchInput.value.toLowerCase().trim();
    const cards = document.querySelectorAll('.card');
    const sections = document.querySelectorAll('.media-section');
    let totalVisible = 0;

    cards.forEach(card => {
        const filename = card.getAttribute('data-filename') || '';
        if (filename.includes(query)) {
            card.style.display = 'flex';
            totalVisible++;
        } else {
            card.style.display = 'none';
        }
    });

    sections.forEach(section => {
        const visibleCards = section.querySelectorAll('.card[style*="display: flex"], .card:not([style*="display: none"])');
        if (query.length > 0 && visibleCards.length === 0) {
            section.style.display = 'none';
        } else {
            section.style.display = 'block';
        }
    });

    const noResultsMsg = document.getElementById('no-results');
    if (noResultsMsg) {
        if (totalVisible === 0 && cards.length > 0) {
            noResultsMsg.style.display = 'block';
        } else {
            noResultsMsg.style.display = 'none';
        }
    }
}

/* DRAG & DROP HANDLING */
document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    if (dropZone) {
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            const fileInput = document.getElementById('file-input');
            if (fileInput) {
                fileInput.files = files;
                updateSelectedCount();
            }
        });
    }
});

/* GLOBAL FOLDER & QUOTA STATE */
window.currentFolderId = null;
window.folderBreadcrumbs = [{ id: null, name: 'Home' }];
window.folderTreeData = [];

/* BATCH UPLOAD LOGIC WITH QUOTA VALIDATION */
let uploadQueue = [];
let totalBytes = 0;
let bytesUploaded = 0;
let startTime = 0;
let completedCount = 0;

function startBatchUpload() {
    const input = document.getElementById('file-input');
    if (!input || input.files.length === 0) {
        alert("Please select or drop files to upload first!");
        return;
    }

    const files = Array.from(input.files);
    const totalBatchBytes = files.reduce((acc, f) => acc + f.size, 0);

    // Validate User Storage Quota
    const quotaBytes = (window.USER_STORAGE_QUOTA_MB || 5000) * 1024 * 1024;
    const usedBytes = window.USER_USED_BYTES || 0;
    const remainingBytes = quotaBytes - usedBytes;

    if (totalBatchBytes > remainingBytes) {
        const reqMB = (totalBatchBytes / (1024 * 1024)).toFixed(1);
        const remMB = Math.max(0, (remainingBytes / (1024 * 1024))).toFixed(1);
        alert(`Storage Quota Exceeded!\n\nYour upload size (${reqMB} MB) exceeds your remaining storage quota of ${remMB} MB.`);
        return;
    }

    uploadQueue = files.map((file, idx) => ({
        id: idx,
        file: file,
        status: 'pending',
        uploadedBytes: 0
    }));

    totalBytes = totalBatchBytes;
    bytesUploaded = 0;
    completedCount = 0;
    startTime = Date.now();

    const queueList = document.getElementById('queue-list');
    if (queueList) {
        queueList.innerHTML = '';
        uploadQueue.forEach(item => {
            const div = document.createElement('div');
            div.className = 'queue-item';
            div.id = `queue-item-${item.id}`;
            div.innerHTML = `
                <span class="queue-filename">${item.file.name}</span>
                <span class="badge badge-pending" id="badge-${item.id}">Pending</span>
            `;
            queueList.appendChild(div);
        });
    }

    const drawer = document.getElementById('upload-drawer');
    if (drawer) drawer.style.display = 'block';

    processNextInQueue();
}

function processNextInQueue() {
    const activeUploads = uploadQueue.filter(i => i.status === 'uploading').length;
    const pendingItems = uploadQueue.filter(i => i.status === 'pending');

    if (activeUploads < MAX_CONCURRENT_UPLOADS && pendingItems.length > 0) {
        const itemToUpload = pendingItems[0];
        uploadSingleFileAJAX(itemToUpload);
        processNextInQueue();
    }
}

function uploadSingleFileAJAX(item) {
    item.status = 'uploading';
    updateBadge(item.id, 'Uploading...', 'badge-uploading');

    const formData = new FormData();
    formData.append('file', item.file);

    // Pass target folder_id if currently inside a virtual folder
    if (window.currentFolderId) {
        formData.append('folder_id', window.currentFolderId);
    }

    const xhr = new XMLHttpRequest();
    xhr.open('POST', getUploadUrl(), true);
    xhr.setRequestHeader('X-CSRFToken', getCsrfToken());

    let previousFileUploaded = 0;

    xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
            const delta = e.loaded - previousFileUploaded;
            previousFileUploaded = e.loaded;
            bytesUploaded += delta;
            updateOverallMetrics();
        }
    };

    xhr.onload = function() {
        if (xhr.status === 200 || xhr.status === 201) {
            item.status = 'done';
            updateBadge(item.id, 'Done', 'badge-done');
            fetchFolderTree();
        } else {
            item.status = 'failed';
            updateBadge(item.id, 'Failed', 'badge-failed');
        }
        completedCount++;
        checkBatchCompletion();
    };

    xhr.onerror = function() {
        item.status = 'failed';
        updateBadge(item.id, 'Failed', 'badge-failed');
        completedCount++;
        checkBatchCompletion();
    };

    xhr.send(formData);
}

function updateBadge(id, text, className) {
    const badge = document.getElementById(`badge-${id}`);
    if (badge) {
        badge.textContent = text;
        badge.className = `badge ${className}`;
    }
}

function updateOverallMetrics() {
    const percent = Math.min(100, Math.round((bytesUploaded / totalBytes) * 100));
    
    const fill = document.getElementById('progress-bar-fill');
    if (fill) fill.style.width = `${percent}%`;

    const percentText = document.getElementById('progress-percent');
    if (percentText) percentText.textContent = `${percent}%`;

    const summaryText = document.getElementById('progress-summary');
    if (summaryText) summaryText.textContent = `Uploading ${completedCount}/${uploadQueue.length} files...`;

    const elapsedTime = (Date.now() - startTime) / 1000;
    if (elapsedTime > 0) {
        const speedMBps = ((bytesUploaded / (1024 * 1024)) / elapsedTime).toFixed(1);
        const speedText = document.getElementById('upload-speed');
        if (speedText) speedText.textContent = `Speed: ${speedMBps} MB/s`;

        const remainingBytes = totalBytes - bytesUploaded;
        const etaSeconds = Math.round(remainingBytes / (bytesUploaded / elapsedTime));
        const etaText = document.getElementById('upload-eta');
        if (etaText && !isNaN(etaSeconds) && isFinite(etaSeconds)) {
            etaText.textContent = `ETA: ${etaSeconds}s`;
        }
    }
}

function checkBatchCompletion() {
    processNextInQueue();
    if (completedCount === uploadQueue.length) {
        const summaryText = document.getElementById('progress-summary');
        if (summaryText) summaryText.textContent = `🎉 All ${uploadQueue.length} files processed!`;

        const fill = document.getElementById('progress-bar-fill');
        if (fill) fill.style.width = '100%';

        const percentText = document.getElementById('progress-percent');
        if (percentText) percentText.textContent = '100%';

        setTimeout(() => {
            window.location.reload();
        }, 1200);
    }
}

/* LIGHTBOX FUNCTIONS */
function openImageLightbox(element) {
    const fullSrc = element.getAttribute('data-fullsrc');
    const filename = element.getAttribute('data-filename');

    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxVideo = document.getElementById('lightbox-video');
    const lightboxPdf = document.getElementById('lightbox-pdf');
    const lightboxDownload = document.getElementById('lightbox-download');
    const lightboxCaption = document.getElementById('lightbox-caption');

    if (!lightbox || !lightboxImg || !lightboxVideo || !lightboxPdf) return;

    lightboxVideo.style.display = 'none';
    lightboxVideo.pause();
    lightboxVideo.src = '';
    
    lightboxPdf.style.display = 'none';
    lightboxPdf.src = '';

    lightboxImg.src = fullSrc;
    lightboxImg.style.display = 'block';

    if (lightboxCaption) lightboxCaption.textContent = filename;
    if (lightboxDownload) {
        lightboxDownload.href = fullSrc;
        lightboxDownload.setAttribute('download', filename);
    }

    lightbox.classList.add('active');
}

function openVideoLightbox(element) {
    const videoSrc = element.getAttribute('data-videosrc');
    const filename = element.getAttribute('data-filename');

    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxVideo = document.getElementById('lightbox-video');
    const lightboxPdf = document.getElementById('lightbox-pdf');
    const lightboxDownload = document.getElementById('lightbox-download');
    const lightboxCaption = document.getElementById('lightbox-caption');

    if (!lightbox || !lightboxImg || !lightboxVideo || !lightboxPdf) return;

    lightboxImg.style.display = 'none';
    lightboxImg.src = '';

    lightboxPdf.style.display = 'none';
    lightboxPdf.src = '';

    lightboxVideo.src = videoSrc;
    lightboxVideo.style.display = 'block';
    lightboxVideo.play();

    if (lightboxCaption) lightboxCaption.textContent = filename;
    if (lightboxDownload) {
        lightboxDownload.href = videoSrc;
        lightboxDownload.setAttribute('download', filename);
    }

    lightbox.classList.add('active');
}

function openPdfLightbox(element) {
    const pdfSrc = element.getAttribute('data-pdfsrc');
    const filename = element.getAttribute('data-filename');

    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxVideo = document.getElementById('lightbox-video');
    const lightboxPdf = document.getElementById('lightbox-pdf');
    const lightboxDownload = document.getElementById('lightbox-download');
    const lightboxCaption = document.getElementById('lightbox-caption');

    if (!lightbox || !lightboxImg || !lightboxVideo || !lightboxPdf) return;

    lightboxImg.style.display = 'none';
    lightboxImg.src = '';

    lightboxVideo.style.display = 'none';
    lightboxVideo.pause();
    lightboxVideo.src = '';

    lightboxPdf.src = pdfSrc;
    lightboxPdf.style.display = 'block';

    if (lightboxCaption) lightboxCaption.textContent = filename;
    if (lightboxDownload) {
        lightboxDownload.href = pdfSrc;
        lightboxDownload.setAttribute('download', filename);
    }

    lightbox.classList.add('active');
}

function closeLightbox(event) {
    if (event.target.id === 'lightbox' || event.target.classList.contains('lightbox-close')) {
        const lightbox = document.getElementById('lightbox');
        if (lightbox) lightbox.classList.remove('active');
        
        const lightboxVideo = document.getElementById('lightbox-video');
        if (lightboxVideo) {
            lightboxVideo.pause();
            lightboxVideo.src = '';
        }

        const lightboxImg = document.getElementById('lightbox-img');
        if (lightboxImg) lightboxImg.src = '';

        const lightboxPdf = document.getElementById('lightbox-pdf');
        if (lightboxPdf) lightboxPdf.src = '';
    }
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const lightbox = document.getElementById('lightbox');
        if (lightbox && lightbox.classList.contains('active')) {
            lightbox.classList.remove('active');
            const lightboxVideo = document.getElementById('lightbox-video');
            if (lightboxVideo) {
                lightboxVideo.pause();
                lightboxVideo.src = '';
            }
            const lightboxImg = document.getElementById('lightbox-img');
            if (lightboxImg) lightboxImg.src = '';
            const lightboxPdf = document.getElementById('lightbox-pdf');
            if (lightboxPdf) lightboxPdf.src = '';
        }
    }
});

/* --- FOLDER TREE & BREADCRUMB REST API INTEGRATION --- */

function fetchFolderTree() {
    fetch('/api/folders/tree/')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                window.folderTreeData = data.tree;
                renderFolderTreeChips(data.tree);
            }
        })
        .catch(err => console.error("Error loading folder tree:", err));
}

function renderFolderTreeChips(tree) {
    const container = document.getElementById('folder-tree-chips');
    if (!container) return;

    let currentSubfolders = tree;
    if (window.currentFolderId) {
        const findFolder = (list, id) => {
            for (let f of list) {
                if (f.id === id) return f;
                if (f.subfolders && f.subfolders.length) {
                    const found = findFolder(f.subfolders, id);
                    if (found) return found;
                }
            }
            return null;
        };
        const currentFolderNode = findFolder(tree, window.currentFolderId);
        if (currentFolderNode && currentFolderNode.subfolders) {
            currentSubfolders = currentFolderNode.subfolders;
        } else {
            currentSubfolders = [];
        }
    }

    if (!currentSubfolders || currentSubfolders.length === 0) {
        container.innerHTML = '<span style="font-size: 0.8rem; color: var(--text-muted);">No subfolders in this directory.</span>';
        return;
    }

    container.innerHTML = currentSubfolders.map(f => `
        <div class="folder-chip ${window.currentFolderId === f.id ? 'active' : ''}" onclick="selectFolder(${f.id}, '${f.name.replace(/'/g, "\\'")}')">
            📁 ${f.name} <span style="font-size: 0.75rem; opacity: 0.7;">(${f.file_count || 0})</span>
        </div>
    `).join('');
}

function selectFolder(folderId, folderName) {
    window.currentFolderId = folderId;

    if (folderId === null) {
        window.folderBreadcrumbs = [{ id: null, name: 'Home' }];
    } else {
        const existingIdx = window.folderBreadcrumbs.findIndex(b => b.id === folderId);
        if (existingIdx !== -1) {
            window.folderBreadcrumbs = window.folderBreadcrumbs.slice(0, existingIdx + 1);
        } else {
            window.folderBreadcrumbs.push({ id: folderId, name: folderName });
        }
    }

    renderBreadcrumbs();
    if (window.folderTreeData) {
        renderFolderTreeChips(window.folderTreeData);
    } else {
        fetchFolderTree();
    }
}

function renderBreadcrumbs() {
    const breadcrumbContainer = document.getElementById('folder-breadcrumbs');
    if (!breadcrumbContainer) return;

    breadcrumbContainer.innerHTML = window.folderBreadcrumbs.map((b, idx) => {
        const isLast = idx === window.folderBreadcrumbs.length - 1;
        if (isLast) {
            return `<span class="breadcrumb-item active">📁 ${b.name}</span>`;
        }
        return `
            <span class="breadcrumb-item" onclick="selectFolder(${b.id}, '${b.name.replace(/'/g, "\\'")}')">📁 ${b.name}</span>
            <span class="breadcrumb-separator">/</span>
        `;
    }).join('');
}

function createNewFolderPrompt() {
    const name = prompt("Enter new folder name:");
    if (!name || !name.trim()) return;

    fetch('/api/folders/create/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
            name: name.trim(),
            parent_id: window.currentFolderId
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            fetchFolderTree();
        } else {
            alert(data.error || "Failed to create folder.");
        }
    })
    .catch(err => {
        console.error("Folder creation error:", err);
        alert("An error occurred creating folder.");
    });
}

document.addEventListener('DOMContentLoaded', function() {
    fetchFolderTree();
});
