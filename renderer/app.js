const app = document.getElementById('app');

const state = {
  appState: { status: 'idle', message: 'Waiting to start.' },
  progress: { stage: 'idle', current: 0, total: 1, message: '' },
  progressLog: [],
  readyLoaded: false,
  index: null,
  assets: [],
  filteredAssets: [],
  selectedAssetId: null,
  selectedAsset: null,
  selectedAnimationName: null,
  previewUrls: {},
  sheetImages: {},
  sheetTransparentImages: {},
  animationPlaying: true,
  animationFrameIndex: 0,
  hideBlackBackground: true,
  exportWidth: 560,
  exportHeight: 420,
  exportFps: 30,
  exportCropToBounds: true,
  exportTransparentBackground: true,
  exportState: 'idle',
  exportMessage: '',
  assetLoadState: 'idle',
  assetLoadMessage: '',
  assetLoadErrors: [],
  rebuildMessage: '',
  validationReport: null,
  settings: null,
  modLibrary: null,
  modpackExportState: 'idle',
  modpackProgress: { stage: 'idle', current: 0, total: 1, message: '' },
  modpackLog: [],
  showModpackSidebar: true,
  query: '',
};

let playbackTimer = null;
let sidebarScrollTop = 0;
let contentScrollTop = 0;
let searchRefreshTimer = null;

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatHex(value) {
  return `0x${Number(value).toString(16)}`;
}

function progressPercent() {
  const total = Math.max(Number(state.progress.total) || 1, 1);
  const current = Math.min(Number(state.progress.current) || 0, total);
  return Math.round((current / total) * 100);
}

function progressPercentFor(progress) {
  const total = Math.max(Number(progress?.total) || 1, 1);
  const current = Math.min(Number(progress?.current) || 0, total);
  return Math.round((current / total) * 100);
}

function getSelectedAnimation() {
  return state.selectedAsset?.animations?.find((animation) => animation.name === state.selectedAnimationName) || null;
}

function sanitizeFileToken(value) {
  return String(value ?? 'asset').replace(/[<>:"/\\|?*\x00-\x1f]+/g, '_').replace(/\s+/g, '_');
}


function clampNumber(value, minimum, maximum, fallback) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return Math.max(minimum, Math.min(maximum, numeric));
}

function captureScrollPositions() {
  sidebarScrollTop = document.querySelector('.asset-list')?.scrollTop || 0;
  contentScrollTop = document.querySelector('.content')?.scrollTop || 0;
}

function restoreScrollPositions() {
  const assetList = document.querySelector('.asset-list');
  const content = document.querySelector('.content');
  if (assetList) {
    assetList.scrollTop = sidebarScrollTop;
  }
  if (content) {
    content.scrollTop = contentScrollTop;
  }
}

function renderBootShell() {
  const status = state.appState.status;
  const title =
    status === 'missing-source'
      ? 'animations.b Not Found'
      : status === 'error'
        ? 'Cache Build Failed'
        : 'Loading animations.b index';
  const body =
    status === 'missing-source'
      ? `The app could not find <span class="mono">animations.b</span> in <span class="mono">${escapeHtml(state.appState.resourcesPath)}</span>. Select the folder that contains <span class="mono">animations.b</span> or the game folder that contains <span class="mono">resources</span>.`
      : escapeHtml(state.progress.message || state.appState.message || 'Preparing cache...');

  const button =
    status === 'missing-source'
      ? `<button class="primary-button" id="pick-folder">Select Folder</button>`
      : '';

  const retry =
    status === 'error'
      ? `<button class="primary-button" id="pick-folder">Pick Another Folder</button>`
      : '';

  const progressBar =
    status === 'loading'
      ? `
        <div class="progress-wrap">
          <div class="progress-label">
            <span>${escapeHtml(state.progress.stage || 'loading')}</span>
            <span>${progressPercent()}%</span>
          </div>
          <div class="progress-bar">
            <div class="progress-bar-fill" style="width: ${progressPercent()}%"></div>
          </div>
        </div>
      `
      : '';

  const logs = state.progressLog.length
    ? `
      <div class="progress-log">
        ${state.progressLog.slice(-10).map((entry) => `<div class="progress-log-line mono">${escapeHtml(entry)}</div>`).join('')}
      </div>
    `
    : '';

  app.innerHTML = `
    <div class="boot-shell">
      <div class="boot-card">
        <div class="eyebrow">TMOI Console Edition - asset viewer &amp; modpack maker</div>
        <div class="boot-title">${title}</div>
        <div class="boot-body">${body}</div>
        ${progressBar}
        <div class="boot-actions">${button}${retry}</div>
        ${logs}
      </div>
    </div>
  `;

  document.getElementById('pick-folder')?.addEventListener('click', async () => {
    await window.isaacApi.selectSourceFolder();
  });
}

function renderNameChips(items, emptyLabel, formatter = (item) => item.name) {
  if (!items.length) {
    return `<div class="muted small">${escapeHtml(emptyLabel)}</div>`;
  }
  return `
    <div class="section-list">
      ${items.map((item) => `<div class="name-chip"><code>${escapeHtml(formatter(item))}</code></div>`).join('')}
    </div>
  `;
}

function renderAssetList() {
  return state.filteredAssets
    .map((asset) => {
      const active = asset.id === state.selectedAssetId ? ' active' : '';
      const animationPill = Number.isFinite(asset.drawableAnimationCount)
        ? `${asset.drawableAnimationCount}/${asset.animationCount || 0} drawable`
        : `${asset.animationCount || '?'} animations`;
      return `
        <button class="asset-card${active}" data-asset-id="${asset.id}">
          <div class="asset-path">${escapeHtml(asset.assetPath)}</div>
          <div class="asset-meta">
            <span class="pill mono">${escapeHtml(formatHex(asset.assetOffset))}</span>
            <span class="pill">${asset.layerCount} layers</span>
            <span class="pill">${animationPill}</span>
            <span class="pill">${asset.previewable ? 'Preview ready' : 'No preview'}</span>
          </div>
        </button>
      `;
    })
    .join('');
}

function bindAssetCardHandlers() {
  document.querySelectorAll('[data-asset-id]').forEach((element) => {
    element.addEventListener('click', async () => {
      await selectAsset(Number(element.getAttribute('data-asset-id')));
    });
  });
}

function refreshAssetList() {
  const assetList = document.querySelector('.asset-list');
  if (!assetList) {
    return;
  }
  const previousScrollTop = assetList.scrollTop;
  assetList.innerHTML = renderAssetList();
  assetList.scrollTop = previousScrollTop;
  bindAssetCardHandlers();
  const searchSummary = document.getElementById('asset-search-summary');
  if (searchSummary) {
    searchSummary.textContent = `${state.filteredAssets.length}/${state.assets.length} actors shown`;
  }
}

function scheduleAssetListRefresh() {
  window.clearTimeout(searchRefreshTimer);
  searchRefreshTimer = window.setTimeout(async () => {
    const previousSelectedAssetId = state.selectedAssetId;
    applyFilter();
    refreshAssetList();
    if (state.selectedAssetId !== previousSelectedAssetId) {
      if (state.selectedAssetId === null) {
        state.selectedAsset = null;
        state.selectedAnimationName = null;
        renderReady();
        return;
      }
      await selectAsset(state.selectedAssetId);
    }
  }, 40);
}

function renderModpackPanel() {
  const settings = state.settings || {};
  const progress = state.modpackProgress || { stage: 'idle', current: 0, total: 1, message: '' };
  const showProgress = state.modpackExportState === 'working';
  const modLibrary = state.modLibrary || { mods: [], modCount: 0 };
  const selectedMods = new Set(settings.selectedMods || []);
  const titleNameValue = settings.customTitleName || settings.detectedTitleName || '';
  const titleIdValue = settings.customTitleId || settings.detectedTitleId || '';
  const contentIdValue = settings.customContentId || settings.detectedContentId || '';
  const detailValue = settings.customDetail || settings.detectedDetail || '';
  const detectedMetadataLines = [
    `param.json: ${settings.detectedParamJsonPath || 'not found'}`,
    `PARAM.SFO: ${settings.paramSfoSourcePath || settings.detectedParamSfoPath || 'not found'}`,
  ];
  const modCards = modLibrary.mods?.length
    ? modLibrary.mods.map((mod) => {
        const counts = mod.counts || {};
        const selected = selectedMods.has(mod.modName);
        const description = mod.metadata?.description || '';
        const blockedXmls = (mod.xmlFiles || []).filter((file) => file.compatibility?.compatible === false && !file.compatibility?.legacyPocketitemsSchema);
        const legacyXmls = (mod.xmlFiles || []).filter((file) => file.compatibility?.legacyPocketitemsSchema);
        return `
          <label class="mod-card${selected ? ' selected' : ''}">
            <div class="mod-card-top">
              <input class="mod-toggle" type="checkbox" data-mod-name="${escapeHtml(mod.modName)}" ${selected ? 'checked' : ''} />
              <div>
                <div class="asset-path">${escapeHtml(mod.metadata?.name || mod.modName)}</div>
                <div class="muted small mono">${escapeHtml(mod.modName)}</div>
              </div>
            </div>
            ${description ? `<div class="muted small">${escapeHtml(description)}</div>` : ''}
            <div class="asset-meta">
              <span class="pill">${counts.xmlConvertible || 0} XML conversions</span>
              <span class="pill">${counts.assetExact || 0} exact assets</span>
              <span class="pill">${counts.assetFoldedDlc || 0} folded DLC paths</span>
              <span class="pill">${counts.assetNeedsConversion || 0} PNG->PCX needed</span>
              <span class="pill">${counts.assetNew || 0} new assets</span>
            </div>
            ${legacyXmls.length ? `<div class="muted small">Legacy XML conversion available: ${escapeHtml(legacyXmls.map((item) => item.relativePath).join(', '))}</div>` : ''}
            ${blockedXmls.length ? `<div class="muted small">Blocked XML files: ${escapeHtml(blockedXmls.map((item) => item.relativePath).join(', '))}</div>` : ''}
          </label>
        `;
      }).join('')
    : `<div class="muted small">No mod folders scanned yet.</div>`;
  return `
    <div class="panel modpack-panel">
      <div class="panel-header">
        <div class="panel-title">Modpack Export</div>
        <div class="panel-subtitle">Build a full copied game folder from vanilla plus rebuilt actors, converted PC mod files, and metadata edits.</div>
      </div>
      <div class="panel-body stack">
        <div class="tool-summary-grid">
          <div class="kv-card">
            <div class="kv-label">Output Root</div>
            <div class="kv-value mono">${escapeHtml(settings.modpackOutputRoot || 'Not configured')}</div>
          </div>
          <div class="kv-card">
            <div class="kv-label">Selected Mods</div>
            <div class="kv-value">${escapeHtml(String((settings.selectedMods || []).length))}</div>
          </div>
        </div>
        <details class="tool-section" open>
          <summary>Export Setup</summary>
          <div class="tool-section-body stack">
            <label class="field">
              <span class="kv-label">Output Folder</span>
              <div class="toolbar">
                <button class="ghost-button" id="select-modpack-output">Choose Output Folder</button>
              </div>
              <div class="muted small mono">${escapeHtml(settings.modpackOutputRoot || 'No output folder configured')}</div>
            </label>
            <label class="field">
              <span class="kv-label">Modpack Name</span>
              <input id="modpack-name" class="search" type="text" value="${escapeHtml(settings.modpackName || '')}" />
            </label>
            <label class="field">
              <span class="kv-label">Replacement Files Folder</span>
              <div class="toolbar">
                <button class="ghost-button" id="select-replacement-files-root">Choose Replacement Folder</button>
              </div>
              <div class="muted small mono">${escapeHtml(settings.replacementFilesRoot || 'Optional. Put changed files here using paths relative to the game root or inside a PPSA03311-app0 mirror.')}</div>
            </label>
          </div>
        </details>
        <details class="tool-section" open>
          <summary>Console Metadata</summary>
          <div class="tool-section-body stack">
            <div class="muted small">Detected from the configured read-only game copy automatically. Manual PARAM.SFO override is optional.</div>
            <div class="progress-log compact-log">
              ${detectedMetadataLines.map((entry) => `<div class="progress-log-line mono">${escapeHtml(entry)}</div>`).join('')}
            </div>
            <label class="field">
              <span class="kv-label">Custom Title</span>
              <input id="custom-title-name" class="search" type="text" value="${escapeHtml(titleNameValue)}" />
            </label>
            <label class="field">
              <span class="kv-label">Custom Title ID</span>
              <input id="custom-title-id" class="search" type="text" value="${escapeHtml(titleIdValue)}" />
            </label>
            <label class="field">
              <span class="kv-label">Custom Content ID</span>
              <input id="custom-content-id" class="search" type="text" value="${escapeHtml(contentIdValue)}" />
            </label>
            <label class="field">
              <span class="kv-label">Detail (SFO)</span>
              <input id="custom-detail" class="search" type="text" value="${escapeHtml(detailValue)}" />
            </label>
            <div class="toolbar">
              <button class="ghost-button" id="select-param-sfo">Choose PARAM.SFO Override</button>
              <button class="ghost-button" id="export-param-template">Export Param Template</button>
            </div>
          </div>
        </details>
        <details class="tool-section" open>
          <summary>PC Mod Library</summary>
          <div class="tool-section-body stack">
            <label class="field">
              <span class="kv-label">PC Mods Folder</span>
              <div class="toolbar">
                <button class="ghost-button" id="select-mods-source-root">Choose Mods Folder</button>
                <button class="ghost-button" id="refresh-mod-library">Refresh Mod Scan</button>
              </div>
              <div class="muted small mono">${escapeHtml(settings.modsSourceRoot || 'Optional. Pick a folder whose subfolders are PC mods.')}</div>
            </label>
            <div class="field">
              <span class="kv-label">Mod Library</span>
              <div class="muted small">Scanned mods: ${modLibrary.modCount || 0}. Selected for export: ${(settings.selectedMods || []).length}.</div>
              <div class="mod-library">${modCards}</div>
            </div>
          </div>
        </details>
        <div class="toolbar">
          <button class="primary-button" id="export-modpack">Export Modpack Copy</button>
        </div>
        ${showProgress ? `
          <div class="progress-wrap">
            <div class="progress-label">
              <span>${escapeHtml(progress.stage || 'export')}</span>
              <span>${progressPercentFor(progress)}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-bar-fill" style="width: ${progressPercentFor(progress)}%"></div>
            </div>
          </div>
        ` : ''}
        ${state.rebuildMessage ? `<div class="muted small">${escapeHtml(state.rebuildMessage)}</div>` : ''}
        <details class="tool-section">
          <summary>Verbose Export Log</summary>
          <div class="tool-section-body">
            <div class="progress-log modpack-log">
          ${(state.modpackLog.length ? state.modpackLog : ['No modpack export log yet.']).slice(-18).map((entry) => `<div class="progress-log-line mono">${escapeHtml(entry)}</div>`).join('')}
            </div>
          </div>
        </details>
      </div>
    </div>
  `;
}

function renderModpackSidebar() {
  return `
    <aside class="right-drawer${state.showModpackSidebar ? '' : ' collapsed'}">
      <div class="right-drawer-header">
        <div>
          <div class="eyebrow">Export Tools</div>
          ${state.showModpackSidebar ? '<div class="drawer-title">Modpack Export Settings</div>' : ''}
        </div>
        <button class="ghost-button drawer-toggle" id="toggle-modpack-sidebar">${state.showModpackSidebar ? 'Collapse' : 'Expand'}</button>
      </div>
      ${state.showModpackSidebar ? `<div class="right-drawer-body">${renderModpackPanel()}</div>` : ''}
    </aside>
  `;
}

function renderAnimationList() {
  const animations = state.selectedAsset?.animations || [];
  if (!animations.length) {
    if (state.selectedAsset?.classification === 'reference-sheet') {
      return `<div class="muted small">This entry looks like a reference spritesheet block, not a standalone actor animation block.</div>`;
    }
    return `<div class="muted small">No parsed animations for this actor.</div>`;
  }
  return animations
    .map((animation) => {
      const active = animation.name === state.selectedAnimationName ? ' active' : '';
      return `
        <button class="asset-card compact${active}" data-animation-name="${escapeHtml(animation.name)}">
          <div class="asset-path">${escapeHtml(animation.name)}</div>
          <div class="asset-meta">
            <span class="pill">${animation.frameNum} frames</span>
            <span class="pill">${animation.loop ? 'Source loop' : 'Source one-shot'}</span>
          </div>
        </button>
      `;
    })
    .join('');
}

function renderSelectedAnimationSummary() {
  const animation = getSelectedAnimation();
  const animations = state.selectedAsset?.animations || [];
  if (!animations.length) {
    if (state.selectedAsset?.classification === 'reference-sheet') {
      return `<div class="muted small">This entry looks like a reference spritesheet block, not a standalone actor animation block.</div>`;
    }
    return `<div class="muted small">No parsed animations for this actor.</div>`;
  }
  if (!animation) {
    return `<div class="muted small">Choose an animation from the preview card to inspect it.</div>`;
  }
  const drawability = analyzeAnimationDrawability(animation);
  return `
    <div class="stack small">
      <div class="asset-meta">
        <span class="pill">${animation.frameNum} frames</span>
        <span class="pill">${animation.loop ? 'Source loop' : 'Source one-shot'}</span>
        <span class="pill">${drawability.hasDrawableFrames ? 'Drawable' : 'Undrawable'}</span>
      </div>
      ${!drawability.hasDrawableFrames ? `<div class="muted small">${escapeHtml(drawability.message)}</div>` : ''}
      <div class="muted small">Use the animation dropdown in the preview card to switch quickly.</div>
    </div>
  `;
}

function renderAnimationPlayer() {
  const animation = getSelectedAnimation();
  if (!animation) {
    return `<div class="muted small">Select an animation to preview it.</div>`;
  }
  const totalFrames = animation.timelineFrames?.length || animation.frameNum || 0;
  const currentFrame = Math.min(state.animationFrameIndex, Math.max(totalFrames - 1, 0));
  const drawability = analyzeAnimationDrawability(animation);
  const animationOptions = (state.selectedAsset?.animations || [])
    .map((item) => `<option value="${escapeHtml(item.name)}" ${item.name === state.selectedAnimationName ? 'selected' : ''}>${escapeHtml(item.name)}</option>`)
    .join('');
  return `
    <div class="animation-player">
      <canvas id="animation-canvas" class="animation-canvas" width="560" height="420"></canvas>
      ${!drawability.hasDrawableFrames ? `<div class="muted small">${escapeHtml(drawability.message)}</div>` : ''}
      <div class="animation-toolbar">
        <label class="field animation-select-field">
          <span class="kv-label">Animation</span>
          <select id="animation-select" class="search">${animationOptions}</select>
        </label>
        <button class="ghost-button" id="toggle-play">${state.animationPlaying ? 'Stop' : 'Play'}</button>
        <button class="ghost-button" id="prev-frame">Prev</button>
        <button class="ghost-button" id="next-frame">Next</button>
        <button class="ghost-button${state.hideBlackBackground ? ' active-toggle' : ''}" id="toggle-black-bg">
          ${state.hideBlackBackground ? 'Black Hidden' : 'Black Visible'}
        </button>
        <button class="ghost-button" id="export-gif" ${state.exportState === 'working' ? 'disabled' : ''}>Export GIF</button>
        <button class="ghost-button" id="export-mp4" ${state.exportState === 'working' ? 'disabled' : ''}>Export MP4</button>
        <button class="ghost-button" id="export-spritesheet" ${state.exportState === 'working' ? 'disabled' : ''}>Export Sheet</button>
        <div class="pill">Frame ${currentFrame + 1}/${totalFrames}</div>
      </div>
      <div class="export-grid">
        <label class="field">
          <span class="kv-label">Width</span>
          <input id="export-width" class="search" type="number" min="64" max="4096" value="${state.exportWidth}" />
        </label>
        <label class="field">
          <span class="kv-label">Height</span>
          <input id="export-height" class="search" type="number" min="64" max="4096" value="${state.exportHeight}" />
        </label>
        <label class="field">
          <span class="kv-label">FPS</span>
          <input id="export-fps" class="search" type="number" min="1" max="120" value="${state.exportFps}" />
        </label>
        <label class="field checkbox-field">
          <input id="export-crop" type="checkbox" ${state.exportCropToBounds ? 'checked' : ''} />
          <span>Crop to animation bounds</span>
        </label>
        <label class="field checkbox-field">
          <input id="export-transparent" type="checkbox" ${state.exportTransparentBackground ? 'checked' : ''} />
          <span>Transparent export background</span>
        </label>
      </div>
      ${state.exportMessage ? `<div class="muted small">${escapeHtml(state.exportMessage)}</div>` : ''}
    </div>
  `;
}

function renderDetails() {
  const asset = state.selectedAsset;
  if (state.assetLoadState === 'loading') {
    return `
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Loading Actor</div>
          <div class="panel-subtitle">${escapeHtml(state.assetLoadMessage || 'Loading sprite sheets and cached detail...')}</div>
        </div>
        <div class="panel-body">
          <div class="progress-wrap">
            <div class="progress-label">
              <span>actor load</span>
              <span>working</span>
            </div>
            <div class="progress-bar">
              <div class="progress-bar-fill progress-bar-indeterminate"></div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  if (state.assetLoadState === 'error') {
    return `
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Actor Load Failed</div>
          <div class="panel-subtitle">${escapeHtml(state.assetLoadMessage || 'The selected actor could not be loaded.')}</div>
        </div>
        <div class="panel-body">
          <div class="progress-log">
            ${state.assetLoadErrors.map((entry) => `<div class="progress-log-line mono">${escapeHtml(entry)}</div>`).join('')}
          </div>
        </div>
      </div>
    `;
  }

  if (!asset) {
    return `<div class="panel"><div class="panel-body muted small">Select an actor on the left.</div></div>`;
  }

  const previewCards = asset.spritesheets.length
    ? asset.spritesheets.map((sheet) => {
        const previewUrl = state.previewUrls[sheet.sheetId];
        const previewError = state.assetLoadErrors.find((entry) => entry.includes(`sheet ${sheet.sheetId}`));
        const previewContent = previewUrl
          ? `<img src="${escapeHtml(previewUrl)}" alt="${escapeHtml(sheet.assetPath)}" />`
          : previewError
            ? `<div class="muted small">${escapeHtml(previewError)}</div>`
            : `<div class="muted small">Preview not generated yet.</div>`;
        return `
          <div class="preview-card">
            <div class="kv-label">Sheet ${sheet.sheetId}</div>
            <div class="preview-frame">${previewContent}</div>
            <div class="muted small mono">${escapeHtml(sheet.assetPath || '')}</div>
          </div>
        `;
      }).join('')
    : `<div class="muted small">No spritesheets were resolved for this actor.</div>`;
  const validationWarnings = asset.validation?.warnings || [];
  const selectedAnimation = getSelectedAnimation();
  const animationDebug = selectedAnimation?.debug || null;
  const headerDecoded = animationDebug?.headerDecoded || null;
  const tailDebug = asset.debug?.tail || null;

  return `
    <div class="content-header">
      <div class="header-grid header-grid-compact">
        <div class="header-identity">
          <div class="eyebrow">Selected Actor</div>
          <div class="title actor-title">${escapeHtml(asset.assetPath)}</div>
          <div class="subtitle actor-subtitle">
            Cached actor block from <span class="mono">${escapeHtml(formatHex(asset.assetOffset))}</span> to
            <span class="mono">${escapeHtml(formatHex(asset.groupEndOffset))}</span>.
          </div>
        </div>
        <div class="stat-strip">
          <div class="stat-pill"><span class="stat-pill-label">Layers</span><span class="stat-pill-value">${asset.layers.length}</span></div>
          <div class="stat-pill"><span class="stat-pill-label">Nulls</span><span class="stat-pill-value">${asset.nulls.length}</span></div>
          <div class="stat-pill"><span class="stat-pill-label">Events</span><span class="stat-pill-value">${asset.events.length}</span></div>
          <div class="stat-pill"><span class="stat-pill-label">Animations</span><span class="stat-pill-value">${asset.animations.length}</span></div>
        </div>
      </div>
    </div>
    <div class="content-body">
      <div class="stack">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Animation Preview</div>
            <div class="panel-subtitle">Layer timelines decoded from animations.b.</div>
          </div>
          <div class="panel-body">${renderAnimationPlayer()}</div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Spritesheets</div>
            <div class="panel-subtitle">Cached previews load from the local cache once generated.</div>
          </div>
          <div class="panel-body stack">${previewCards}</div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Layers</div>
          </div>
          <div class="panel-body">
            ${renderNameChips(asset.layers, 'No layers', (item) => `${item.id}:${item.sheetId} ${item.name}`)}
          </div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Validation</div>
            <div class="panel-subtitle">Automated anomaly checks across parsed animation data.</div>
          </div>
          <div class="panel-body">
            <div class="toolbar" style="margin-bottom: 12px;">
              <button class="ghost-button" id="export-editable-actor">Export Editable JSON</button>
              <button class="ghost-button" id="rebuild-actor-bundle">Rebuild From Edited JSON</button>
              <button class="ghost-button" id="verify-raw-roundtrip">Verify Raw Roundtrip</button>
              <button class="ghost-button" id="verify-structured-roundtrip">Verify Structured Roundtrip</button>
            </div>
            ${validationWarnings.length
              ? `<div class="progress-log">${validationWarnings.map((warning) => `<div class="progress-log-line">${escapeHtml(warning)}</div>`).join('')}</div>`
              : `<div class="muted small">No validation warnings for this actor.</div>`}
            ${state.rebuildMessage ? `<div class="muted small" style="margin-top: 12px;">${escapeHtml(state.rebuildMessage)}</div>` : ''}
          </div>
        </div>
      </div>
      <div class="stack">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Selected Animation</div>
            <div class="panel-subtitle">Parsed from the packed PS5 layout and switched from the preview card dropdown.</div>
          </div>
          <div class="panel-body">
            ${renderSelectedAnimationSummary()}
          </div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Nulls and Events</div>
          </div>
          <div class="panel-body stack">
            <div>
              <div class="kv-label">Null Names</div>
              <div style="margin-top: 12px;">${renderNameChips(asset.nulls, 'No nulls')}</div>
            </div>
            <div>
              <div class="kv-label">Event Names</div>
              <div style="margin-top: 12px;">${renderNameChips(asset.events, 'No events')}</div>
            </div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Research View</div>
            <div class="panel-subtitle">Tail coverage, candidate event refs, and unresolved binary regions.</div>
          </div>
          <div class="panel-body stack">
            <div class="kv-grid">
              <div class="kv-card">
                <div class="kv-label">Animation Tail</div>
                <div class="kv-value mono">
                  start ${escapeHtml(formatHex(asset.debug?.animationDataOffset || 0))}<br />
                  end ${escapeHtml(formatHex(asset.groupEndOffset))}<br />
                  coverage ${escapeHtml(String(tailDebug?.parsedCoverage ?? 'n/a'))}
                </div>
              </div>
              <div class="kv-card">
                <div class="kv-label">Selected Animation</div>
                <div class="kv-value mono">
                  confidence ${escapeHtml(String(animationDebug?.parseConfidence ?? 'n/a'))}<br />
                  header len ${escapeHtml(String(animationDebug?.headerLength ?? 'n/a'))}<br />
                  layer count @ ${escapeHtml(formatHex(animationDebug?.layerCountOffset || 0))}
                </div>
              </div>
            </div>
            <div>
              <div class="kv-label">Sheet Mapping</div>
              <div class="progress-log">
                ${asset.spritesheets.map((sheet) => `<div class="progress-log-line mono">sheet ${sheet.sheetId}: ${escapeHtml(sheet.assetPath || 'unresolved')} [${escapeHtml(sheet.mappingMethod || 'n/a')}, conf ${escapeHtml(String(sheet.mappingConfidence ?? 'n/a'))}]</div>`).join('')}
              </div>
            </div>
            <div>
              <div class="kv-label">Selected Header Bytes</div>
              <div class="hex-block">${escapeHtml(animationDebug?.headerHex || 'Select an animation to inspect header bytes.')}</div>
            </div>
            <div>
              <div class="kv-label">Decoded Header</div>
              <div class="progress-log">
                ${headerDecoded
                  ? Object.entries(headerDecoded).map(([key, value]) => `<div class="progress-log-line mono">${escapeHtml(key)}: ${escapeHtml(String(value))}</div>`).join('')
                  : '<div class="progress-log-line mono">No decoded header available.</div>'}
              </div>
            </div>
            <div>
              <div class="kv-label">Candidate Event Timeline Refs</div>
              <div class="progress-log">
                ${(animationDebug?.eventTimeline?.length
                  ? animationDebug.eventTimeline.map((eventRef) => `<div class="progress-log-line mono">frame~${eventRef.frameIndexHint}: ${escapeHtml(eventRef.eventName)} (${eventRef.eventId})</div>`).join('')
                  : '<div class="progress-log-line mono">No candidate event refs found in the current animation header.</div>')}
              </div>
            </div>
            <div>
              <div class="kv-label">Tail Gap Samples</div>
              <div class="progress-log">
                ${(tailDebug?.gaps?.length
                  ? tailDebug.gaps.map((gap) => `<div class="progress-log-line mono">${escapeHtml(formatHex(gap.startOffset))}-${escapeHtml(formatHex(gap.endOffset))} len=${gap.length} tokens=${escapeHtml((gap.asciiTokens || []).join(', ') || 'none')}</div>`).join('')
                  : '<div class="progress-log-line mono">No gap samples captured.</div>')}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function ensureSheetImage(sheetId, url) {
  if (!url) {
    return Promise.resolve(null);
  }
  if (state.sheetImages[sheetId]?.src === url) {
    return Promise.resolve(state.sheetImages[sheetId]);
  }
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      state.sheetImages[sheetId] = image;
      resolve(image);
    };
    image.onerror = () => reject(new Error(`sheet ${sheetId}: failed to load cached preview image`));
    image.src = url;
  });
}

function buildTransparentSheetImage(image) {
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth || image.width;
  canvas.height = image.naturalHeight || image.height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(image, 0, 0);
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const pixels = imageData.data;
  for (let index = 0; index < pixels.length; index += 4) {
    if (pixels[index] === 0 && pixels[index + 1] === 0 && pixels[index + 2] === 0) {
      pixels[index + 3] = 0;
    }
  }
  ctx.putImageData(imageData, 0, 0);
  return canvas;
}

function getDrawableSheetImage(sheetId) {
  const source = state.sheetImages[sheetId];
  if (!source) {
    return null;
  }
  if (!state.hideBlackBackground) {
    return source;
  }
  if (!state.sheetTransparentImages[sheetId]) {
    state.sheetTransparentImages[sheetId] = buildTransparentSheetImage(source);
  }
  return state.sheetTransparentImages[sheetId];
}

function analyzeAnimationDrawability(animation) {
  const frames = animation?.timelineFrames || [];
  const framesWithLayerData = frames.filter((frame) => (frame?.layers || []).length > 0).length;
  const framesWithVisibleLayers = frames.filter((frame) => (frame?.layers || []).some((layer) => layer.visible)).length;
  const missingSheetIds = new Set();
  const unresolvedSheetIds = new Set();

  for (const frame of frames) {
    for (const layer of frame?.layers || []) {
      if (!layer.visible) {
        continue;
      }
      const sheet = (state.selectedAsset?.spritesheets || []).find((item) => item.sheetId === layer.sheetId);
      if (!sheet || !sheet.assetPath || !sheet.resourceExists) {
        missingSheetIds.add(layer.sheetId);
        continue;
      }
      if (!getDrawableSheetImage(layer.sheetId)) {
        unresolvedSheetIds.add(layer.sheetId);
      }
    }
  }

  const hasDrawableFrames = frames.some((frame) => collectVisibleLayers(frame).length > 0);
  if (hasDrawableFrames) {
    return { hasDrawableFrames: true, message: '' };
  }
  if (!frames.length) {
    return { hasDrawableFrames: false, message: 'This parsed animation has no timeline frames.' };
  }
  if (!framesWithLayerData) {
    return { hasDrawableFrames: false, message: 'This parsed animation has no layer timeline data to draw.' };
  }
  if (!framesWithVisibleLayers) {
    return { hasDrawableFrames: false, message: 'This parsed animation only contains hidden layer frames.' };
  }
  if (missingSheetIds.size) {
    return {
      hasDrawableFrames: false,
      message: `This animation has layer data, but sheet ids ${[...missingSheetIds].join(', ')} are unresolved or missing.`,
    };
  }
  if (unresolvedSheetIds.size) {
    return {
      hasDrawableFrames: false,
      message: `This animation references sheets ${[...unresolvedSheetIds].join(', ')}, but their preview images did not load.`,
    };
  }
  return {
    hasDrawableFrames: false,
    message: 'This parsed animation has frame data, but none of its frames are currently drawable.',
  };
}

function collectVisibleLayers(frame) {
  return [...(frame?.layers || [])]
    .filter((layer) => layer.visible && getDrawableSheetImage(layer.sheetId))
    .sort((left, right) => left.layerId - right.layerId);
}

function getFrameBounds(frame) {
  const visibleLayers = collectVisibleLayers(frame);
  if (!visibleLayers.length) {
    return null;
  }

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const layer of visibleLayers) {
    const width = Math.abs(layer.width * layer.xScale);
    const height = Math.abs(layer.height * layer.yScale);
    const left = layer.xPosition - Math.abs(layer.xPivot * layer.xScale);
    const top = layer.yPosition - Math.abs(layer.yPivot * layer.yScale);
    minX = Math.min(minX, left);
    minY = Math.min(minY, top);
    maxX = Math.max(maxX, left + width);
    maxY = Math.max(maxY, top + height);
  }

  return { minX, minY, maxX, maxY, visibleLayers };
}

function computeAnimationBounds(animation) {
  const timeline = animation?.timelineFrames || [];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let found = false;
  for (const frame of timeline) {
    const bounds = getFrameBounds(frame);
    if (!bounds) {
      continue;
    }
    found = true;
    minX = Math.min(minX, bounds.minX);
    minY = Math.min(minY, bounds.minY);
    maxX = Math.max(maxX, bounds.maxX);
    maxY = Math.max(maxY, bounds.maxY);
  }
  return found ? { minX, minY, maxX, maxY } : null;
}

function drawFrameToCanvas(canvas, frameIndex, options = {}) {
  const animation = getSelectedAnimation();
  if (!animation || !canvas) {
    return false;
  }

  const ctx = canvas.getContext('2d');
  const timeline = animation.timelineFrames || [];
  const frame = timeline[Math.min(frameIndex, Math.max(timeline.length - 1, 0))];
  if (!options.transparentBackground) {
    ctx.fillStyle = '#101823';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  } else {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  if (!frame) {
    return false;
  }

  const bounds = options.bounds || getFrameBounds(frame);
  if (!bounds) {
    const drawability = analyzeAnimationDrawability(animation);
    ctx.fillStyle = '#9fb2c5';
    ctx.font = '14px Segoe UI';
    const lines = (drawability.message || 'No drawable layers for this frame.').match(/.{1,58}(\s|$)/g) || ['No drawable layers for this frame.'];
    lines.slice(0, 4).forEach((line, index) => {
      ctx.fillText(line.trim(), 20, 28 + (index * 22));
    });
    return false;
  }

  const { minX, minY, maxX, maxY } = bounds;
  const visibleLayers = getFrameBounds(frame)?.visibleLayers || [];
  const root = frame.root || {};
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const scale = Math.min((canvas.width - 40) / spanX, (canvas.height - 40) / spanY);

  ctx.save();
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.scale(scale, scale);
  ctx.translate(-(minX + maxX) / 2, -(minY + maxY) / 2);
  ctx.translate(root.xPosition || 0, root.yPosition || 0);
  ctx.rotate(((root.rotation || 0) * Math.PI) / 180);
  ctx.scale(root.xScale || 1, root.yScale || 1);
  ctx.globalAlpha = Math.max(0, Math.min(1, root.alphaTint ?? 1));

  for (const layer of visibleLayers) {
    const image = getDrawableSheetImage(layer.sheetId);
    ctx.save();
    ctx.translate(layer.xPosition, layer.yPosition);
    ctx.rotate((layer.rotation || 0) * Math.PI / 180);
    ctx.scale(layer.xScale || 1, layer.yScale || 1);
    ctx.globalAlpha = Math.max(0, Math.min(1, layer.alphaTint ?? 1));
    ctx.drawImage(
      image,
      layer.xCrop,
      layer.yCrop,
      layer.width,
      layer.height,
      -layer.xPivot,
      -layer.yPivot,
      layer.width,
      layer.height,
    );
    ctx.restore();
  }

  ctx.restore();
  return true;
}

function drawAnimationFrame() {
  const canvas = document.getElementById('animation-canvas');
  if (!canvas) {
    return;
  }
  drawFrameToCanvas(canvas, state.animationFrameIndex);
}

function syncAnimationUi() {
  drawAnimationFrame();
}

async function runValidationAction(action, fallbackMessage) {
  try {
    await action();
  } catch (error) {
    state.rebuildMessage = `${fallbackMessage}: ${error?.message || 'Unknown error'}`;
    renderReady();
    syncAnimationUi();
  }
}

function renderReady() {
  captureScrollPositions();
  app.innerHTML = `
    <div class="app-shell${state.showModpackSidebar ? '' : ' app-shell-drawer-collapsed'}">
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="title title-compact">TMOI Console Edition</div>
          <div class="sidebar-header-grid">
            <div class="kv-card">
              <div class="kv-label">Source Folder</div>
              <div class="kv-value mono">${escapeHtml(state.appState.resourcesPath || '')}</div>
            </div>
            ${state.validationReport ? `
              <div class="kv-card">
                <div class="kv-label">Validation</div>
                <div class="kv-value">${state.validationReport.warningAssetCount}/${state.validationReport.assetCount} sampled actors flagged</div>
              </div>
            ` : ''}
          </div>
          <div class="toolbar">
            <button class="ghost-button" id="pick-folder">Change Folder</button>
            <button class="ghost-button" id="export-zip">Export Zip</button>
          </div>
        </div>
        <div class="search-wrap">
          <input id="asset-search" class="search" type="search" placeholder="Filter actors by path" value="${escapeHtml(state.query)}" />
          <div id="asset-search-summary" class="muted small" style="margin-top: 10px;">${state.filteredAssets.length}/${state.assets.length} actors shown</div>
        </div>
        <div class="asset-list">${renderAssetList()}</div>
      </aside>
      <main class="content">${renderDetails()}</main>
      ${renderModpackSidebar()}
    </div>
  `;

  document.getElementById('toggle-modpack-sidebar')?.addEventListener('click', () => {
    state.showModpackSidebar = !state.showModpackSidebar;
    renderReady();
    syncAnimationUi();
  });

  document.getElementById('pick-folder')?.addEventListener('click', async () => {
    await window.isaacApi.selectSourceFolder();
  });

  document.getElementById('export-zip')?.addEventListener('click', async () => {
    const result = await window.isaacApi.exportZip();
    if (result?.zipPath) {
      state.progressLog.push(`Exported zip: ${result.zipPath}`);
      render();
    }
  });

  document.getElementById('asset-search')?.addEventListener('input', (event) => {
    state.query = event.target.value;
    scheduleAssetListRefresh();
  });

  document.getElementById('select-modpack-output')?.addEventListener('click', async () => {
    const result = await window.isaacApi.selectModpackOutputFolder();
    if (!result?.canceled) {
      state.settings = { ...(state.settings || {}), modpackOutputRoot: result.modpackOutputRoot };
      renderReady();
      syncAnimationUi();
    }
  });

  document.getElementById('select-param-sfo')?.addEventListener('click', async () => {
    const result = await window.isaacApi.selectParamSfoSource();
    if (!result?.canceled) {
      state.settings = { ...(state.settings || {}), paramSfoSourcePath: result.paramSfoSourcePath };
      renderReady();
      syncAnimationUi();
    }
  });

  document.getElementById('select-replacement-files-root')?.addEventListener('click', async () => {
    const result = await window.isaacApi.selectReplacementFilesFolder();
    if (!result?.canceled) {
      state.settings = { ...(state.settings || {}), replacementFilesRoot: result.replacementFilesRoot };
      renderReady();
      syncAnimationUi();
    }
  });

  document.getElementById('select-mods-source-root')?.addEventListener('click', async () => {
    const result = await window.isaacApi.selectModsSourceFolder();
    if (!result?.canceled) {
      state.settings = { ...(state.settings || {}), modsSourceRoot: result.modsSourceRoot, selectedMods: [] };
      state.modLibrary = await window.isaacApi.getModLibrary();
      renderReady();
      syncAnimationUi();
    }
  });

  document.getElementById('refresh-mod-library')?.addEventListener('click', async () => {
    state.modLibrary = await window.isaacApi.getModLibrary();
    renderReady();
    syncAnimationUi();
  });

  document.getElementById('export-param-template')?.addEventListener('click', async () => {
    await runValidationAction(async () => {
      const result = await window.isaacApi.exportParamBundle();
      state.rebuildMessage = `Param edit template exported: ${result.jsonPath}`;
      renderReady();
      syncAnimationUi();
    }, 'Param template export failed');
  });

  const persistSettings = async (patch) => {
    state.settings = await window.isaacApi.saveSettings({ ...(state.settings || {}), ...patch });
  };

  document.getElementById('modpack-name')?.addEventListener('change', async (event) => {
    await persistSettings({ modpackName: event.target.value });
  });
  document.getElementById('custom-title-name')?.addEventListener('change', async (event) => {
    await persistSettings({ customTitleName: event.target.value });
  });
  document.getElementById('custom-title-id')?.addEventListener('change', async (event) => {
    await persistSettings({ customTitleId: event.target.value });
  });
  document.getElementById('custom-content-id')?.addEventListener('change', async (event) => {
    await persistSettings({ customContentId: event.target.value });
  });
  document.getElementById('custom-detail')?.addEventListener('change', async (event) => {
    await persistSettings({ customDetail: event.target.value });
  });

  document.querySelectorAll('[data-mod-name]').forEach((element) => {
    element.addEventListener('change', async (event) => {
      const modName = element.getAttribute('data-mod-name');
      const next = new Set(state.settings?.selectedMods || []);
      if (event.target.checked) {
        next.add(modName);
      } else {
        next.delete(modName);
      }
      await persistSettings({ selectedMods: [...next] });
      renderReady();
      syncAnimationUi();
    });
  });

  document.getElementById('export-modpack')?.addEventListener('click', async () => {
    state.modpackExportState = 'working';
    state.modpackProgress = { stage: 'prepare', current: 0, total: 1, message: 'Starting modpack export...' };
    state.modpackLog = [`[prepare] Starting export for ${(state.settings?.modpackName || 'IsaacModpack')}`];
    renderReady();
    syncAnimationUi();
    try {
      await persistSettings({
        modpackName: document.getElementById('modpack-name')?.value || '',
        customTitleName: document.getElementById('custom-title-name')?.value || '',
        customTitleId: document.getElementById('custom-title-id')?.value || '',
        customContentId: document.getElementById('custom-content-id')?.value || '',
        customDetail: document.getElementById('custom-detail')?.value || '',
      });
      const result = await window.isaacApi.exportModpack(state.settings || {});
      state.rebuildMessage =
        `Modpack exported: ${result.gameCopyRoot} ` +
        `(${result.patchedActorCount || 0} actor patches, ${result.replacementFileCount || 0} replacement files)`;
      if (result.modOverlayReport) {
        state.modpackLog.push(
          `[mods] Imported ${(result.modOverlayReport.processedMods || []).length} selected mods, ` +
          `${result.modOverlayReport.mergedXmlFiles || 0} merged XML files, ` +
          `${result.modOverlayReport.copiedAssets || 0} copied assets`
        );
        for (const entry of (result.modOverlayReport.skippedFiles || []).slice(0, 12)) {
          state.modpackLog.push(`[mods] skipped ${entry.modName || ''} ${entry.relativePath || ''} ${entry.reason || ''}`.trim());
        }
      }
    } catch (error) {
      state.rebuildMessage = `Modpack export failed: ${error?.message || 'Unknown error'}`;
    } finally {
      state.modpackExportState = 'idle';
      renderReady();
      syncAnimationUi();
    }
  });

  document.getElementById('export-editable-actor')?.addEventListener('click', async () => {
    await runValidationAction(async () => {
      if (state.selectedAssetId === null) {
        throw new Error('No actor is selected.');
      }
      const result = await window.isaacApi.exportEditableActor(state.selectedAssetId);
      state.rebuildMessage = `Editable actor JSON exported: ${result.jsonPath}`;
      renderReady();
      syncAnimationUi();
    }, 'Editable actor export failed');
  });

  document.getElementById('rebuild-actor-bundle')?.addEventListener('click', async () => {
    await runValidationAction(async () => {
      const result = await window.isaacApi.rebuildActorBundle();
      if (result?.canceled) {
        state.rebuildMessage = 'Rebuild canceled.';
      } else {
        state.rebuildMessage = result.matchesOriginal
          ? `Rebuilt actor bytes from edited JSON: ${result.binPath} (matches original SHA)`
          : `Rebuilt actor bytes from edited JSON: ${result.binPath} (SHA changed from original, ready for patching)`;
      }
      renderReady();
      syncAnimationUi();
    }, 'Actor rebuild failed');
  });

  document.getElementById('verify-raw-roundtrip')?.addEventListener('click', async () => {
    await runValidationAction(async () => {
      if (state.selectedAssetId === null) {
        throw new Error('No actor is selected.');
      }
      const result = await window.isaacApi.verifyActorRoundtrip(state.selectedAssetId, false);
      state.rebuildMessage = result.matchesOriginal
        ? `Raw-preserved roundtrip matched original bytes (${result.originalLength} bytes).`
        : `Raw-preserved roundtrip mismatch at relative byte ${result.firstMismatchOffset}.`;
      renderReady();
      syncAnimationUi();
    }, 'Raw roundtrip verification failed');
  });

  document.getElementById('verify-structured-roundtrip')?.addEventListener('click', async () => {
    await runValidationAction(async () => {
      if (state.selectedAssetId === null) {
        throw new Error('No actor is selected.');
      }
      const result = await window.isaacApi.verifyActorRoundtrip(state.selectedAssetId, true);
      state.rebuildMessage = result.matchesOriginal
        ? `Structured roundtrip matched original bytes (${result.originalLength} bytes).`
        : `Structured roundtrip mismatch at relative byte ${result.firstMismatchOffset}.`;
      renderReady();
      syncAnimationUi();
    }, 'Structured roundtrip verification failed');
  });

  bindAssetCardHandlers();

  document.getElementById('animation-select')?.addEventListener('change', (event) => {
      state.selectedAnimationName = event.target.value;
      state.animationFrameIndex = 0;
      state.animationPlaying = true;
      renderReady();
      syncAnimationUi();
  });

  document.getElementById('toggle-play')?.addEventListener('click', () => {
    state.animationPlaying = !state.animationPlaying;
    if (state.animationPlaying) {
      const animation = getSelectedAnimation();
      const total = animation?.timelineFrames?.length || 0;
      if (total > 0 && state.animationFrameIndex >= total - 1) {
        state.animationFrameIndex = 0;
      }
    }
    renderReady();
    syncAnimationUi();
  });

  document.getElementById('toggle-black-bg')?.addEventListener('click', () => {
    state.hideBlackBackground = !state.hideBlackBackground;
    renderReady();
    syncAnimationUi();
  });

  document.getElementById('export-gif')?.addEventListener('click', async () => {
    await exportSelectedAnimation('gif');
  });

  document.getElementById('export-mp4')?.addEventListener('click', async () => {
    await exportSelectedAnimation('mp4');
  });

  document.getElementById('export-spritesheet')?.addEventListener('click', async () => {
    await exportSelectedSpritesheet();
  });

  document.getElementById('export-width')?.addEventListener('input', (event) => {
    state.exportWidth = clampNumber(event.target.value, 64, 4096, 560);
  });

  document.getElementById('export-height')?.addEventListener('input', (event) => {
    state.exportHeight = clampNumber(event.target.value, 64, 4096, 420);
  });

  document.getElementById('export-fps')?.addEventListener('input', (event) => {
    state.exportFps = clampNumber(event.target.value, 1, 120, state.selectedAsset?.fps || 30);
  });

  document.getElementById('export-crop')?.addEventListener('change', (event) => {
    state.exportCropToBounds = event.target.checked;
  });

  document.getElementById('export-transparent')?.addEventListener('change', (event) => {
    state.exportTransparentBackground = event.target.checked;
  });

  document.getElementById('prev-frame')?.addEventListener('click', () => {
    const animation = getSelectedAnimation();
    const total = animation?.timelineFrames?.length || 1;
    state.animationFrameIndex = (state.animationFrameIndex - 1 + total) % total;
    state.animationPlaying = false;
    renderReady();
    syncAnimationUi();
  });

  document.getElementById('next-frame')?.addEventListener('click', () => {
    const animation = getSelectedAnimation();
    const total = animation?.timelineFrames?.length || 1;
    state.animationFrameIndex = (state.animationFrameIndex + 1) % total;
    state.animationPlaying = false;
    renderReady();
    syncAnimationUi();
  });

  restoreScrollPositions();
  syncAnimationUi();
}

function render() {
  if (state.appState.status !== 'ready') {
    renderBootShell();
    return;
  }
  renderReady();
}

function applyFilter() {
  const query = state.query.trim().toLowerCase();
  state.filteredAssets = !query
    ? [...state.assets]
    : state.assets.filter((asset) => asset.assetPath.toLowerCase().includes(query));
  if (state.selectedAssetId === null) {
    state.selectedAssetId = state.filteredAssets[0]?.id ?? null;
  }
}

async function selectAsset(assetId) {
  captureScrollPositions();
  state.selectedAssetId = assetId;
  state.assetLoadState = 'loading';
  state.assetLoadMessage = 'Parsing actor detail and generating preview cache files...';
  state.assetLoadErrors = [];
  state.rebuildMessage = '';
  state.selectedAsset = null;
  state.selectedAnimationName = null;
  state.previewUrls = {};
  state.sheetImages = {};
  state.sheetTransparentImages = {};
  state.animationFrameIndex = 0;
  state.animationPlaying = true;
  state.exportFps = 30;
  state.exportState = 'idle';
  state.exportMessage = '';
  render();

  try {
    state.selectedAsset = await window.isaacApi.getAsset(assetId);
    state.selectedAnimationName = state.selectedAsset.animations[0]?.name || null;
    state.exportFps = state.selectedAsset.fps || 30;
    const animationCount = state.selectedAsset.animations.length;
    const drawableAnimationCount = Number(state.selectedAsset.validation?.stats?.drawableAnimationCount || 0);
    state.assets = state.assets.map((asset) => (
      asset.id === assetId ? { ...asset, animationCount, drawableAnimationCount } : asset
    ));
    applyFilter();
    state.assetLoadMessage = 'Caching spritesheet previews...';
    render();
    const previews = await window.isaacApi.ensurePreviews(assetId);
    state.previewUrls = Object.fromEntries(previews.map((entry) => [entry.sheetId, entry.previewUrl]));
    state.assetLoadErrors = previews
      .filter((entry) => !entry.previewUrl)
      .map((entry) => `sheet ${entry.sheetId}: preview was not generated or no source sheet was available`);
    for (const entry of previews) {
      if (!entry.previewUrl) {
        continue;
      }
      try {
        await ensureSheetImage(entry.sheetId, entry.previewUrl);
      } catch (error) {
        state.assetLoadErrors.push(error.message);
      }
    }
    state.assetLoadState = 'idle';
  } catch (error) {
    state.assetLoadState = 'error';
    state.assetLoadMessage = error?.message || 'Unknown actor load failure.';
    state.assetLoadErrors = [state.assetLoadMessage];
  }

  render();
}

async function loadReadyData() {
  if (state.readyLoaded) {
    return;
  }
  state.settings = await window.isaacApi.getSettings();
  state.index = await window.isaacApi.getIndex();
  state.validationReport = await window.isaacApi.validateAnimations(60);
  state.modLibrary = await window.isaacApi.getModLibrary();
  state.assets = state.index?.assets || [];
  applyFilter();
  state.readyLoaded = true;
  render();
  if (state.selectedAssetId !== null) {
    await selectAsset(state.selectedAssetId);
  }
}

function handleBootstrapEvent(event) {
  if (event.type === 'state') {
    state.appState = event.payload;
    if (state.appState.status !== 'ready') {
      state.readyLoaded = false;
      state.index = null;
      state.assets = [];
      state.validationReport = null;
      state.selectedAsset = null;
      state.selectedAnimationName = null;
      state.previewUrls = {};
      state.sheetImages = {};
      state.assetLoadState = 'idle';
      state.assetLoadErrors = [];
    }
    render();
    if (state.appState.status === 'ready') {
      loadReadyData().catch((error) => {
        state.appState = { status: 'error', message: error.message };
        render();
      });
    }
    return;
  }

  if (event.type === 'progress') {
    const nextProgress = {
      stage: event.stage,
      current: event.current,
      total: event.total,
      message: event.message,
    };
    state.progress = nextProgress;
    state.progressLog.push(`[${event.stage}] ${event.message}`);
    if (state.appState.status === 'ready' && state.modpackExportState === 'working') {
      state.modpackProgress = nextProgress;
      state.modpackLog.push(`[${event.stage}] ${event.message}`);
    }
    render();
  }
}

function tickPlayback() {
  if (state.appState.status !== 'ready' || state.assetLoadState !== 'idle' || !state.animationPlaying) {
    return;
  }
  const animation = getSelectedAnimation();
  const total = animation?.timelineFrames?.length || 0;
  if (!total) {
    return;
  }
  state.animationFrameIndex += 1;
  if (state.animationFrameIndex >= total) {
    state.animationFrameIndex = 0;
  }
  syncAnimationUi();
}

async function exportSelectedAnimation(format) {
  const animation = getSelectedAnimation();
  if (!animation || state.exportState === 'working') {
    return;
  }

  state.exportState = 'working';
  state.exportMessage = `Rendering ${format.toUpperCase()} frames...`;
  renderReady();
  syncAnimationUi();

  try {
    const total = animation.timelineFrames?.length || animation.frameNum || 0;
    const exportCanvas = document.createElement('canvas');
    exportCanvas.width = state.exportWidth;
    exportCanvas.height = state.exportHeight;
    const frames = [];
    const bounds = state.exportCropToBounds ? computeAnimationBounds(animation) : null;

    for (let frameIndex = 0; frameIndex < total; frameIndex += 1) {
      drawFrameToCanvas(exportCanvas, frameIndex, {
        bounds,
        transparentBackground: state.exportTransparentBackground,
      });
      frames.push(exportCanvas.toDataURL('image/png'));
    }

    state.exportMessage = `Encoding ${format.toUpperCase()}...`;
    renderReady();
    syncAnimationUi();

    const assetToken = sanitizeFileToken(state.selectedAsset?.assetPath || 'actor');
    const animationToken = sanitizeFileToken(animation.name || 'animation');
    const result = await window.isaacApi.exportAnimation({
      format,
      fps: state.exportFps,
      defaultName: `${assetToken}_${animationToken}`,
      frames,
    });

    state.exportMessage = result?.canceled
      ? `${format.toUpperCase()} export canceled.`
      : `Exported ${format.toUpperCase()}: ${result.filePath}`;
  } catch (error) {
    state.exportMessage = `${format.toUpperCase()} export failed: ${error?.message || 'Unknown error'}`;
  } finally {
    state.exportState = 'idle';
    renderReady();
    syncAnimationUi();
  }
}

async function exportSelectedSpritesheet() {
  const animation = getSelectedAnimation();
  if (!animation || state.exportState === 'working') {
    return;
  }

  state.exportState = 'working';
  state.exportMessage = 'Packing animation spritesheet...';
  renderReady();
  syncAnimationUi();

  try {
    const total = animation.timelineFrames?.length || animation.frameNum || 0;
    const cols = Math.max(1, Math.ceil(Math.sqrt(total)));
    const rows = Math.max(1, Math.ceil(total / cols));
    const frameCanvas = document.createElement('canvas');
    frameCanvas.width = state.exportWidth;
    frameCanvas.height = state.exportHeight;
    const atlasCanvas = document.createElement('canvas');
    atlasCanvas.width = cols * state.exportWidth;
    atlasCanvas.height = rows * state.exportHeight;
    const atlasCtx = atlasCanvas.getContext('2d');
    const bounds = state.exportCropToBounds ? computeAnimationBounds(animation) : null;
    const frameMetadata = [];

    for (let frameIndex = 0; frameIndex < total; frameIndex += 1) {
      drawFrameToCanvas(frameCanvas, frameIndex, {
        bounds,
        transparentBackground: state.exportTransparentBackground,
      });
      const x = (frameIndex % cols) * state.exportWidth;
      const y = Math.floor(frameIndex / cols) * state.exportHeight;
      atlasCtx.drawImage(frameCanvas, x, y);
      frameMetadata.push({
        frameIndex,
        x,
        y,
        width: state.exportWidth,
        height: state.exportHeight,
      });
    }

    const assetToken = sanitizeFileToken(state.selectedAsset?.assetPath || 'actor');
    const animationToken = sanitizeFileToken(animation.name || 'animation');
    const result = await window.isaacApi.exportSpritesheet({
      defaultName: `${assetToken}_${animationToken}_sheet`,
      pngDataUrl: atlasCanvas.toDataURL('image/png'),
      metadata: {
        assetPath: state.selectedAsset?.assetPath || '',
        animationName: animation.name,
        fps: state.exportFps,
        frameWidth: state.exportWidth,
        frameHeight: state.exportHeight,
        columns: cols,
        rows,
        cropToBounds: state.exportCropToBounds,
        transparentBackground: state.exportTransparentBackground,
        hideBlackBackground: state.hideBlackBackground,
        frames: frameMetadata,
      },
    });
    state.exportMessage = result?.canceled
      ? 'Spritesheet export canceled.'
      : `Exported spritesheet: ${result.pngPath}`;
  } catch (error) {
    state.exportMessage = `Spritesheet export failed: ${error?.message || 'Unknown error'}`;
  } finally {
    state.exportState = 'idle';
    renderReady();
    syncAnimationUi();
  }
}

async function boot() {
  if (!playbackTimer) {
    playbackTimer = window.setInterval(tickPlayback, 1000 / 30);
  }
  state.appState = await window.isaacApi.getAppState();
  window.isaacApi.onBootstrapEvent(handleBootstrapEvent);
  render();
  if (state.appState.status === 'ready') {
    await loadReadyData();
  }
}

boot().catch((error) => {
  state.appState = { status: 'error', message: error.message };
  render();
});
