/**
 * MCP Router Dashboard - State Management
 * Modular stores with get/set/subscribe pattern.
 */

// Generic store factory
function createStore(initialState = {}) {
  let state = { ...initialState };
  const listeners = new Set();

  return {
    get() {
      return { ...state };
    },
    set(updates) {
      state = { ...state, ...updates };
      listeners.forEach((cb) => cb(state));
    },
    subscribe(callback) {
      listeners.add(callback);
      return () => listeners.delete(callback);
    },
    _reset() {
      state = { ...initialState };
      listeners.forEach((cb) => cb(state));
    },
  };
}

// Auth Store
export const authStore = createStore({
  token: window.sessionStorage.getItem("dashboardBearerToken") || "",
  status: "optional", // 'optional' | 'loaded' | 'error'
});

// Setup Store - manages the setup wizard flow
export const setupStore = createStore({
  step: 1, // 1, 2, 3
  selectedClient: "claude_code",
  scope: "user",
  preview: null,
  verification: null,
  configPath: "",
  serverName: "mcp-router",
  mcpUrl: `${window.location.origin}/mcp`,
});

// Registry Store - data entities
export const registryStore = createStore({
  clients: [],
  upstreams: [],
  tools: [],
  candidates: [],
  authEnabled: false,
  defaultMcpUrl: `${window.location.origin}/mcp`,
});

// Operations Store - control plane data
export const operationsStore = createStore({
  policies: [],
  toolCalls: [],
  events: [],
});

// UI Store - interface state
export const uiStore = createStore({
  activeTab: "connect", // 'connect' | 'import' | 'operations'
  socket: null,
  globalStatus: {
    tone: "info",
    message: "Loading dashboard...",
  },
  loading: {
    setup: false,
    import: false,
    operations: false,
  },
});

// Convenience getters
export function getAuthToken() {
  return authStore.get().token;
}

export function setAuthToken(token) {
  const trimmed = token.trim();
  authStore.set({ token: trimmed, status: trimmed ? "loaded" : "optional" });
  if (trimmed) {
    window.sessionStorage.setItem("dashboardBearerToken", trimmed);
  } else {
    window.sessionStorage.removeItem("dashboardBearerToken");
  }
}

export function getSelectedClient() {
  return setupStore.get().selectedClient;
}

export function setSelectedClient(clientId) {
  setupStore.set({ selectedClient: clientId });
}

export function getActiveTab() {
  return uiStore.get().activeTab;
}

export function setActiveTab(tab) {
  uiStore.set({ activeTab: tab });
}

export function isLoading(section) {
  return uiStore.get().loading[section] || false;
}

export function setLoading(section, value) {
  const loading = { ...uiStore.get().loading, [section]: value };
  uiStore.set({ loading });
}

export function setGlobalStatus(tone, message) {
  uiStore.set({ globalStatus: { tone, message } });
}

// Batch updates for registry data
export function setRegistryData(data) {
  registryStore.set({
    clients: data.clients || [],
    upstreams: data.upstreams || [],
    tools: data.tools || [],
    candidates: data.candidates || [],
    authEnabled: data.authEnabled || false,
    defaultMcpUrl: data.defaultMcpUrl || `${window.location.origin}/mcp`,
  });
}

export function setOperationsData(data) {
  operationsStore.set({
    policies: data.policies || [],
    toolCalls: data.toolCalls || [],
    events: data.events || [],
  });
}

// Reset functions
export function resetSetup() {
  setupStore.set({
    step: 1,
    preview: null,
    verification: null,
  });
}

export function resetAllStores() {
  authStore._reset();
  setupStore._reset();
  registryStore._reset();
  operationsStore._reset();
  uiStore._reset();
}
