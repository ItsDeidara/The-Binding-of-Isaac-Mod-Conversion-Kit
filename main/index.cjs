const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { pathToFileURL } = require('url');
const ffmpegPath = require('ffmpeg-static');

const APP_ROOT = path.resolve(__dirname, '..');
const APP_ICON_PATH = path.join(APP_ROOT, 'assets', 'app-icon.png');
const PYTHON_SCRIPT = path.join(APP_ROOT, 'python', 'parse_animations.py');
const XML_HANDLER_SCRIPT = path.join(APP_ROOT, 'python', 'xmlHandler.py');
const CACHE_ROOT = path.join(APP_ROOT, 'cache');
const CACHE_INDEX_PATH = path.join(CACHE_ROOT, 'index.json');
const SETTINGS_PATH = path.join(CACHE_ROOT, 'settings.json');
const DEFAULT_RESOURCES_PATH = path.join(path.resolve(APP_ROOT, '..', '..'), 'PPSA03311-app0', 'resources');
const DEFAULT_GAME_ROOT = path.join(path.resolve(APP_ROOT, '..', '..'), 'PPSA03311-app0');

let mainWindow = null;
let bootstrapPromise = null;
let indexCache = null;
let appState = {
  status: 'idle',
  message: 'Waiting to start.',
  resourcesPath: DEFAULT_RESOURCES_PATH,
};

function ensureCacheDir() {
  fs.mkdirSync(CACHE_ROOT, { recursive: true });
}

function detectMetadataSources(gameRootPath) {
  const gameRoot = gameRootPath || DEFAULT_GAME_ROOT;
  const sceSysRoot = path.join(gameRoot, 'sce_sys');
  const detectedParamJsonPath = path.join(sceSysRoot, 'param.json');
  const detectedParamSfoPath = path.join(sceSysRoot, 'PARAM.SFO');
  return {
    detectedParamJsonPath: fs.existsSync(detectedParamJsonPath) ? detectedParamJsonPath : '',
    detectedParamSfoPath: fs.existsSync(detectedParamSfoPath) ? detectedParamSfoPath : '',
  };
}

function readDetectedParamJson(paramJsonPath) {
  if (!paramJsonPath || !fs.existsSync(paramJsonPath)) {
    return {};
  }
  try {
    const payload = JSON.parse(fs.readFileSync(paramJsonPath, 'utf-8'));
    const localized = payload.localizedParameters || {};
    const defaultLanguage = localized.defaultLanguage || Object.keys(localized).find((key) => key !== 'defaultLanguage') || '';
    const languageBlock = defaultLanguage ? (localized[defaultLanguage] || {}) : {};
    return {
      titleName: languageBlock.titleName || '',
      titleId: payload.titleId || '',
      contentId: payload.contentId || '',
      detail: '',
      subtitle: languageBlock.subTitle || languageBlock.subtitle || '',
    };
  } catch {
    return {};
  }
}

function parseSfoBytes(data) {
  if (!data || data.length < 20) {
    return {};
  }
  if (data.readUInt32BE(0) !== 0x00505346) {
    return {};
  }
  const keyTableStart = data.readUInt32LE(8);
  const dataTableStart = data.readUInt32LE(12);
  const entryCount = data.readUInt32LE(16);
  const values = {};
  for (let index = 0; index < entryCount; index += 1) {
    const base = 20 + (index * 16);
    const keyOffset = data.readUInt16LE(base);
    const dataFmt = data.readUInt16LE(base + 2);
    const dataLen = data.readUInt32LE(base + 4);
    const dataMaxLen = data.readUInt32LE(base + 8);
    const dataOffset = data.readUInt32LE(base + 12);
    const keyStart = keyTableStart + keyOffset;
    let keyEnd = keyStart;
    while (keyEnd < data.length && data[keyEnd] !== 0) {
      keyEnd += 1;
    }
    const key = data.subarray(keyStart, keyEnd).toString('utf-8');
    const valueStart = dataTableStart + dataOffset;
    const valueRaw = data.subarray(valueStart, valueStart + dataMaxLen);
    const valueUsed = valueRaw.subarray(0, Math.min(dataLen, valueRaw.length));
    let value = '';
    if (dataFmt === 0x0404) {
      value = valueUsed.length >= 4 ? String(valueUsed.readUInt32LE(0)) : '0';
    } else {
      const trimmed = (dataFmt === 0x0402 && valueUsed[valueUsed.length - 1] === 0)
        ? valueUsed.subarray(0, valueUsed.length - 1)
        : valueUsed;
      value = trimmed.toString('utf-8');
    }
    values[key] = value;
  }
  return values;
}

function readDetectedParamSfo(paramSfoPath) {
  if (!paramSfoPath || !fs.existsSync(paramSfoPath)) {
    return {};
  }
  try {
    const values = parseSfoBytes(fs.readFileSync(paramSfoPath));
    return {
      titleName: values.TITLE || '',
      titleId: values.TITLE_ID || '',
      contentId: values.CONTENT_ID || '',
      detail: values.DETAIL || '',
      subtitle: values.SUB_TITLE || '',
    };
  } catch {
    return {};
  }
}

function detectMetadataDefaults(gameRootPath, paramSfoSourcePath = '') {
  const sources = detectMetadataSources(gameRootPath);
  const paramJsonDefaults = readDetectedParamJson(sources.detectedParamJsonPath);
  const paramSfoDefaults = readDetectedParamSfo(paramSfoSourcePath || sources.detectedParamSfoPath);
  return {
    detectedTitleName: paramJsonDefaults.titleName || paramSfoDefaults.titleName || '',
    detectedTitleId: paramJsonDefaults.titleId || paramSfoDefaults.titleId || '',
    detectedContentId: paramJsonDefaults.contentId || paramSfoDefaults.contentId || '',
    detectedDetail: paramSfoDefaults.detail || '',
    detectedSubtitle: paramJsonDefaults.subtitle || paramSfoDefaults.subtitle || '',
  };
}

function hydrateSettings(rawSettings = {}) {
  const merged = {
    resourcesPath: DEFAULT_RESOURCES_PATH,
    gameRootPath: DEFAULT_GAME_ROOT,
    modpackOutputRoot: '',
    modpackName: 'IsaacModpack',
    replacementFilesRoot: '',
    modsSourceRoot: '',
    selectedMods: [],
    paramSfoSourcePath: '',
    customTitleName: '',
    customTitleId: '',
    customContentId: '',
    customDetail: '',
    customSubtitle: '',
    ...rawSettings,
  };
  const metadataSources = detectMetadataSources(merged.gameRootPath);
  const metadataDefaults = detectMetadataDefaults(merged.gameRootPath, merged.paramSfoSourcePath);
  return {
    ...merged,
    ...metadataSources,
    ...metadataDefaults,
  };
}

function loadSettings() {
  ensureCacheDir();
  try {
    return hydrateSettings(JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf-8')));
  } catch {
    return hydrateSettings();
  }
}

function saveSettings(settings) {
  ensureCacheDir();
  const current = loadSettings();
  const next = { ...current, ...settings };
  delete next.detectedParamJsonPath;
  delete next.detectedParamSfoPath;
  delete next.detectedTitleName;
  delete next.detectedTitleId;
  delete next.detectedContentId;
  delete next.detectedDetail;
  delete next.detectedSubtitle;
  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(next));
}

function getResourcesPath() {
  return loadSettings().resourcesPath || DEFAULT_RESOURCES_PATH;
}

function getGameRootPath() {
  return loadSettings().gameRootPath || DEFAULT_GAME_ROOT;
}

function parserEnv() {
  return {
    ...process.env,
    ISAAC_RESOURCES_PATH: getResourcesPath(),
  };
}

function sendBootstrapEvent(event) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('bootstrap:event', event);
  }
}

function setAppState(nextState) {
  appState = {
    ...appState,
    ...nextState,
    resourcesPath: getResourcesPath(),
  };
  sendBootstrapEvent({ type: 'state', payload: appState });
}

function runParser(args) {
  return new Promise((resolve, reject) => {
    const py = spawn('python', [PYTHON_SCRIPT, ...args], {
      cwd: APP_ROOT,
      env: parserEnv(),
      windowsHide: true,
    });

    let stdout = '';
    let stderr = '';

    py.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });

    py.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    py.on('error', reject);
    py.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || stdout || `Python exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error(`Failed to parse Python output: ${stdout}`));
      }
    });
  });
}

function runXmlHandler(args) {
  return new Promise((resolve, reject) => {
    const py = spawn('python', [XML_HANDLER_SCRIPT, ...args], {
      cwd: APP_ROOT,
      windowsHide: true,
    });

    let stdout = '';
    let stderr = '';

    py.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });

    py.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    py.on('error', reject);
    py.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || stdout || `Python exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error(`Failed to parse Python output: ${stdout}`));
      }
    });
  });
}

function runFfmpeg(args) {
  return new Promise((resolve, reject) => {
    const proc = spawn(ffmpegPath, args, {
      cwd: APP_ROOT,
      windowsHide: true,
    });

    let stderr = '';
    proc.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    proc.on('error', reject);
    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `ffmpeg exited with code ${code}`));
        return;
      }
      resolve();
    });
  });
}

async function exportAnimation(payload) {
  const format = payload?.format === 'gif' ? 'gif' : 'mp4';
  const filters = format === 'gif'
    ? [{ name: 'GIF Animation', extensions: ['gif'] }]
    : [{ name: 'MP4 Video', extensions: ['mp4'] }];

  const saveResult = await dialog.showSaveDialog(mainWindow, {
    title: `Export ${format.toUpperCase()} Animation`,
    defaultPath: `${payload.defaultName}.${format}`,
    filters,
  });

  if (saveResult.canceled || !saveResult.filePath) {
    return { canceled: true };
  }

  ensureCacheDir();
  const tempRoot = path.join(CACHE_ROOT, 'render-export-temp', `${Date.now()}-${Math.random().toString(16).slice(2)}`);
  fs.mkdirSync(tempRoot, { recursive: true });

  try {
    for (let index = 0; index < payload.frames.length; index += 1) {
      const frame = payload.frames[index];
      const pngData = frame.replace(/^data:image\/png;base64,/, '');
      fs.writeFileSync(path.join(tempRoot, `frame_${String(index).padStart(4, '0')}.png`), Buffer.from(pngData, 'base64'));
    }

    const inputPattern = path.join(tempRoot, 'frame_%04d.png');
    const outputPath = saveResult.filePath;
    const fps = Math.max(1, Number(payload.fps) || 30);

    if (format === 'gif') {
      await runFfmpeg([
        '-y',
        '-framerate', String(fps),
        '-i', inputPattern,
        '-filter_complex', 'split[s0][s1];[s0]palettegen=reserve_transparent=1[p];[s1][p]paletteuse',
        outputPath,
      ]);
    } else {
      await runFfmpeg([
        '-y',
        '-framerate', String(fps),
        '-i', inputPattern,
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        outputPath,
      ]);
    }

    return {
      canceled: false,
      format,
      filePath: outputPath,
      fileUrl: pathToFileURL(outputPath).href,
    };
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

async function exportSpritesheet(payload) {
  const saveResult = await dialog.showSaveDialog(mainWindow, {
    title: 'Export Packed Animation Spritesheet',
    defaultPath: `${payload.defaultName}.png`,
    filters: [{ name: 'PNG Image', extensions: ['png'] }],
  });

  if (saveResult.canceled || !saveResult.filePath) {
    return { canceled: true };
  }

  const pngData = payload.pngDataUrl.replace(/^data:image\/png;base64,/, '');
  const pngPath = saveResult.filePath;
  const jsonPath = pngPath.replace(/\.png$/i, '.json');
  fs.writeFileSync(pngPath, Buffer.from(pngData, 'base64'));
  fs.writeFileSync(jsonPath, JSON.stringify(payload.metadata, null, 2));
  return {
    canceled: false,
    pngPath,
    jsonPath,
    pngUrl: pathToFileURL(pngPath).href,
    jsonUrl: pathToFileURL(jsonPath).href,
  };
}

function streamEnsureCache() {
  return new Promise((resolve, reject) => {
    const py = spawn('python', [PYTHON_SCRIPT, 'ensure-cache-stream'], {
      cwd: APP_ROOT,
      env: parserEnv(),
      windowsHide: true,
    });

    let stderr = '';
    let buffer = '';
    let finalPayload = null;

    py.stdout.on('data', (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) {
          continue;
        }
        try {
          const event = JSON.parse(line);
          if (event.type === 'result') {
            finalPayload = event.payload;
          } else {
            sendBootstrapEvent(event);
          }
        } catch {
          sendBootstrapEvent({
            type: 'progress',
            stage: 'log',
            current: 0,
            total: 1,
            message: line,
          });
        }
      }
    });

    py.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    py.on('error', reject);
    py.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `Python exited with code ${code}`));
        return;
      }
      resolve(finalPayload);
    });
  });
}

function loadIndexCache() {
  indexCache = JSON.parse(fs.readFileSync(CACHE_INDEX_PATH, 'utf-8'));
  return indexCache;
}

async function bootstrapCache() {
  if (bootstrapPromise) {
    return bootstrapPromise;
  }

  bootstrapPromise = (async () => {
    const resourcesPath = getResourcesPath();
    setAppState({
      status: 'loading',
      message: 'Preparing cache…',
      resourcesPath,
    });

    if (!fs.existsSync(path.join(resourcesPath, 'animations.b'))) {
      setAppState({
        status: 'missing-source',
        message: 'animations.b was not found in the configured folder.',
      });
      return null;
    }

    try {
      await streamEnsureCache();
      const index = loadIndexCache();
      setAppState({
        status: 'ready',
        message: `Loaded ${index.assetCount} cached actor entries.`,
      });
      return index;
    } catch (error) {
      setAppState({
        status: 'error',
        message: error.message,
      });
      throw error;
    } finally {
      bootstrapPromise = null;
    }
  })();

  return bootstrapPromise;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: '#12161d',
    icon: APP_ICON_PATH,
    webPreferences: {
      preload: path.join(APP_ROOT, 'renderer', 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadFile(path.join(APP_ROOT, 'renderer', 'index.html'));
  mainWindow.webContents.once('did-finish-load', () => {
    sendBootstrapEvent({ type: 'state', payload: appState });
  });
}

async function selectSourceFolder() {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select the folder that contains animations.b',
  });

  if (result.canceled || !result.filePaths.length) {
    return { canceled: true };
  }

  const chosen = result.filePaths[0];
  let resourcesPath = chosen;
  if (fs.existsSync(path.join(chosen, 'resources', 'animations.b'))) {
    resourcesPath = path.join(chosen, 'resources');
  }
  const gameRootPath = path.dirname(resourcesPath);

  saveSettings({ resourcesPath, gameRootPath });
  await bootstrapCache();
  return { canceled: false, resourcesPath, gameRootPath };
}

async function selectModpackOutputFolder() {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
    title: 'Select the base output folder for exported modpacks',
  });

  if (result.canceled || !result.filePaths.length) {
    return { canceled: true };
  }

  const modpackOutputRoot = result.filePaths[0];
  saveSettings({ modpackOutputRoot });
  return { canceled: false, modpackOutputRoot };
}

async function selectReplacementFilesFolder() {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
    title: 'Select the folder containing replacement files for modpack export',
  });

  if (result.canceled || !result.filePaths.length) {
    return { canceled: true };
  }

  const replacementFilesRoot = result.filePaths[0];
  saveSettings({ replacementFilesRoot });
  return { canceled: false, replacementFilesRoot };
}

async function selectModsSourceFolder() {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select the folder that contains PC mods in subfolders',
  });

  if (result.canceled || !result.filePaths.length) {
    return { canceled: true };
  }

  const modsSourceRoot = result.filePaths[0];
  saveSettings({ modsSourceRoot, selectedMods: [] });
  return { canceled: false, modsSourceRoot };
}

async function getModLibrary() {
  const settings = loadSettings();
  if (!settings.modsSourceRoot || !fs.existsSync(settings.modsSourceRoot)) {
    return { modsRoot: settings.modsSourceRoot || '', modCount: 0, mods: [] };
  }
  return runXmlHandler(['compare-mod-root', settings.modsSourceRoot, settings.gameRootPath || getGameRootPath()]);
}

function copyDirContents(sourceRoot, destinationRoot) {
  if (!sourceRoot || !fs.existsSync(sourceRoot)) {
    return;
  }
  for (const entry of fs.readdirSync(sourceRoot, { withFileTypes: true })) {
    const sourcePath = path.join(sourceRoot, entry.name);
    const destinationPath = path.join(destinationRoot, entry.name);
    if (entry.isDirectory()) {
      fs.mkdirSync(destinationPath, { recursive: true });
      copyDirContents(sourcePath, destinationPath);
    } else {
      fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
      fs.copyFileSync(sourcePath, destinationPath);
    }
  }
}

async function buildSelectedModsOverlay(settings) {
  const selectedMods = Array.isArray(settings.selectedMods) ? settings.selectedMods.filter(Boolean) : [];
  if (!settings.modsSourceRoot || !selectedMods.length) {
    return { overlayRoot: settings.replacementFilesRoot || '', report: null };
  }

  ensureCacheDir();
  const generatedOverlayRoot = path.join(CACHE_ROOT, 'mod-import-overlay');
  fs.rmSync(generatedOverlayRoot, { recursive: true, force: true });
  fs.mkdirSync(generatedOverlayRoot, { recursive: true });
  const configPath = path.join(CACHE_ROOT, 'mod-import-overlay-config.json');
  fs.writeFileSync(
    configPath,
    JSON.stringify({
      modsRoot: settings.modsSourceRoot,
      outputRoot: generatedOverlayRoot,
      gameRoot: settings.gameRootPath || getGameRootPath(),
      selectedMods,
    }),
  );
  const report = await runXmlHandler(['build-mod-overlay', configPath]);

  if (settings.replacementFilesRoot && fs.existsSync(settings.replacementFilesRoot)) {
    const combinedRoot = path.join(CACHE_ROOT, 'combined-replacement-overlay');
    fs.rmSync(combinedRoot, { recursive: true, force: true });
    fs.mkdirSync(combinedRoot, { recursive: true });
    copyDirContents(settings.replacementFilesRoot, combinedRoot);
    copyDirContents(generatedOverlayRoot, combinedRoot);
    return { overlayRoot: combinedRoot, report };
  }

  return { overlayRoot: generatedOverlayRoot, report };
}

async function selectParamSfoSource() {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    title: 'Select a PARAM.SFO source file',
    filters: [{ name: 'PARAM.SFO', extensions: ['sfo', 'SFO'] }],
  });

  if (result.canceled || !result.filePaths.length) {
    return { canceled: true };
  }

  const paramSfoSourcePath = result.filePaths[0];
  saveSettings({ paramSfoSourcePath });
  return { canceled: false, paramSfoSourcePath };
}

function streamModpackExport(configPath) {
  return new Promise((resolve, reject) => {
    const py = spawn('python', [PYTHON_SCRIPT, 'export-modpack-stream', configPath], {
      cwd: APP_ROOT,
      env: parserEnv(),
      windowsHide: true,
    });

    let stderr = '';
    let buffer = '';
    let finalPayload = null;

    py.stdout.on('data', (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) {
          continue;
        }
        try {
          const event = JSON.parse(line);
          if (event.type === 'result') {
            finalPayload = event.payload;
          } else {
            sendBootstrapEvent(event);
          }
        } catch {
          sendBootstrapEvent({
            type: 'progress',
            stage: 'log',
            current: 0,
            total: 1,
            message: line,
          });
        }
      }
    });

    py.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    py.on('error', reject);
    py.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `Python exited with code ${code}`));
        return;
      }
      resolve(finalPayload);
    });
  });
}

async function pickEditableActorBundle() {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    title: 'Select an editable actor JSON bundle',
    filters: [{ name: 'JSON Files', extensions: ['json'] }],
    defaultPath: path.join(CACHE_ROOT, 'export', 'editable-actors'),
  });

  if (result.canceled || !result.filePaths.length) {
    return { canceled: true };
  }

  return { canceled: false, filePath: result.filePaths[0] };
}

app.whenReady().then(() => {
  ipcMain.handle('app:get-state', async () => appState);
  ipcMain.handle('settings:get', async () => loadSettings());
  ipcMain.handle('settings:save', async (_event, nextSettings) => {
    saveSettings(nextSettings || {});
    return loadSettings();
  });
  ipcMain.handle('cache:get-index', async () => {
    if (appState.status !== 'ready') {
      return null;
    }
    return indexCache || loadIndexCache();
  });
  ipcMain.handle('cache:get-asset', async (_event, assetId) => {
    return runParser(['get-asset', String(assetId)]);
  });
  ipcMain.handle('cache:ensure-previews', async (_event, assetId) => {
    const payload = await runParser(['ensure-asset-previews', String(assetId)]);
    return payload.map((entry) => ({
      sheetId: entry.sheetId,
      previewUrl: entry.previewPath ? pathToFileURL(entry.previewPath).href : null,
    }));
  });
  ipcMain.handle('cache:export-editable-actor', async (_event, assetId) => {
    return runParser(['export-editable-actor', String(assetId)]);
  });
  ipcMain.handle('metadata:export-param-bundle', async () => {
    const settings = loadSettings();
    const paramSfoPath = settings.paramSfoSourcePath || settings.detectedParamSfoPath || '';
    return runParser([
      'export-param-bundle',
      ...(paramSfoPath ? ['--param-sfo', paramSfoPath] : []),
    ]);
  });
  ipcMain.handle('cache:rebuild-actor-bundle', async () => {
    const picked = await pickEditableActorBundle();
    if (picked.canceled) {
      return { canceled: true };
    }
    const payload = await runParser(['rebuild-actor-bundle', picked.filePath]);
    return {
      canceled: false,
      ...payload,
      binUrl: payload.binPath ? pathToFileURL(payload.binPath).href : null,
      manifestUrl: payload.manifestPath ? pathToFileURL(payload.manifestPath).href : null,
    };
  });
  ipcMain.handle('cache:verify-actor-roundtrip', async (_event, assetId, structured) => {
    return runParser([
      'verify-actor-roundtrip',
      String(assetId),
      ...(structured ? ['--structured'] : []),
    ]);
  });
  ipcMain.handle('cache:export-zip', async () => {
    const payload = await runParser(['export-cache-zip']);
    return {
      zipPath: payload.zipPath,
      zipUrl: payload.zipPath ? pathToFileURL(payload.zipPath).href : null,
    };
  });
  ipcMain.handle('modpack:select-output-folder', async () => selectModpackOutputFolder());
  ipcMain.handle('mods:select-source-folder', async () => selectModsSourceFolder());
  ipcMain.handle('mods:get-library', async () => getModLibrary());
  ipcMain.handle('modpack:select-replacement-files-folder', async () => selectReplacementFilesFolder());
  ipcMain.handle('metadata:select-param-sfo', async () => selectParamSfoSource());
  ipcMain.handle('modpack:export', async (_event, overrideConfig) => {
    const settings = { ...loadSettings(), ...(overrideConfig || {}) };
    if (!settings.modpackOutputRoot) {
      throw new Error('No modpack output folder is configured.');
    }
    const modOverlay = await buildSelectedModsOverlay(settings);
  const configPayload = {
      outputRoot: settings.modpackOutputRoot,
      modpackName: settings.modpackName || 'IsaacModpack',
      sourceGameRoot: settings.gameRootPath || getGameRootPath(),
      rebuiltActorsDir: path.join(CACHE_ROOT, 'export', 'rebuilt-actors'),
      replacementFilesRoot: modOverlay.overlayRoot || settings.replacementFilesRoot || '',
      metadata: {
        titleName: settings.customTitleName || '',
        titleId: settings.customTitleId || '',
        contentId: settings.customContentId || '',
        detail: settings.customDetail || '',
        subtitle: settings.customSubtitle || '',
        paramSfoSourcePath: settings.paramSfoSourcePath || settings.detectedParamSfoPath || '',
      },
    };
    ensureCacheDir();
    const configPath = path.join(CACHE_ROOT, 'modpack-export-config.json');
    fs.writeFileSync(configPath, JSON.stringify(configPayload));
    const payload = await streamModpackExport(configPath);
    return { ...payload, modOverlayReport: modOverlay.report };
  });
  ipcMain.handle('animation:export', async (_event, payload) => exportAnimation(payload));
  ipcMain.handle('animation:export-spritesheet', async (_event, payload) => exportSpritesheet(payload));
  ipcMain.handle('cache:validate-animations', async (_event, limit) => {
    return runParser(['validate-animations', ...(limit ? ['--limit', String(limit)] : [])]);
  });
  ipcMain.handle('source:select-folder', async () => selectSourceFolder());

  createWindow();
  bootstrapCache().catch(() => {});

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
      bootstrapCache().catch(() => {});
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
