const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('isaacApi', {
  getAppState: () => ipcRenderer.invoke('app:get-state'),
  getSettings: () => ipcRenderer.invoke('settings:get'),
  saveSettings: (payload) => ipcRenderer.invoke('settings:save', payload),
  getIndex: () => ipcRenderer.invoke('cache:get-index'),
  getAsset: (assetId) => ipcRenderer.invoke('cache:get-asset', assetId),
  ensurePreviews: (assetId) => ipcRenderer.invoke('cache:ensure-previews', assetId),
  exportEditableActor: (assetId) => ipcRenderer.invoke('cache:export-editable-actor', assetId),
  exportParamBundle: () => ipcRenderer.invoke('metadata:export-param-bundle'),
  rebuildActorBundle: () => ipcRenderer.invoke('cache:rebuild-actor-bundle'),
  verifyActorRoundtrip: (assetId, structured = false) => ipcRenderer.invoke('cache:verify-actor-roundtrip', assetId, structured),
  validateAnimations: (limit) => ipcRenderer.invoke('cache:validate-animations', limit),
  exportZip: () => ipcRenderer.invoke('cache:export-zip'),
  exportModpack: (payload) => ipcRenderer.invoke('modpack:export', payload),
  exportAnimation: (payload) => ipcRenderer.invoke('animation:export', payload),
  exportSpritesheet: (payload) => ipcRenderer.invoke('animation:export-spritesheet', payload),
  getModLibrary: () => ipcRenderer.invoke('mods:get-library'),
  selectSourceFolder: () => ipcRenderer.invoke('source:select-folder'),
  selectModsSourceFolder: () => ipcRenderer.invoke('mods:select-source-folder'),
  selectModpackOutputFolder: () => ipcRenderer.invoke('modpack:select-output-folder'),
  selectReplacementFilesFolder: () => ipcRenderer.invoke('modpack:select-replacement-files-folder'),
  selectParamSfoSource: () => ipcRenderer.invoke('metadata:select-param-sfo'),
  onBootstrapEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('bootstrap:event', listener);
    return () => ipcRenderer.removeListener('bootstrap:event', listener);
  },
});
