"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("backend", {
  getStatus: () => ipcRenderer.invoke("backend:get-status"),
  probe: () => ipcRenderer.invoke("backend:probe"),
  onStatus: (cb) => {
    const handler = (_event, status) => cb(status);
    ipcRenderer.on("backend-status", handler);
    return () => ipcRenderer.removeListener("backend-status", handler);
  },
});
