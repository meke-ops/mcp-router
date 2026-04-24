/**
 * MCP Router Dashboard - API Client
 * Handles all HTTP and WebSocket communication with the backend.
 */

// Default base URL for MCP endpoint
export function defaultMcpUrl() {
  return `${window.location.origin}/mcp`;
}

// Split comma-separated values
export function splitCsv(value) {
  if (!value) return [];
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

// Build request headers with optional auth token
export function buildHeaders(token, extraHeaders = {}) {
  const headers = new Headers({
    "Content-Type": "application/json",
    ...extraHeaders,
  });
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

// Generic JSON fetch wrapper
export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

// Authenticated fetch wrapper
export async function apiGet(url, token) {
  return fetchJson(url, {
    headers: buildHeaders(token),
  });
}

export async function apiPost(url, token, body) {
  return fetchJson(url, {
    method: "POST",
    headers: buildHeaders(token),
    body: JSON.stringify(body),
  });
}

export async function apiDelete(url, token) {
  return fetchJson(url, {
    method: "DELETE",
    headers: buildHeaders(token),
  });
}

// WebSocket connection manager
export function createWebSocket(token, onMessage, onOpen, onClose) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const query = new URLSearchParams();
  if (token) {
    query.set("access_token", token);
  }
  const socketUrl = `${protocol}//${window.location.host}/v1/events/ws${query.toString() ? `?${query.toString()}` : ""}`;
  
  const socket = new WebSocket(socketUrl);
  
  socket.addEventListener("open", () => {
    if (onOpen) onOpen();
  });
  
  socket.addEventListener("close", () => {
    if (onClose) onClose();
  });
  
  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (onMessage) onMessage(payload);
  });
  
  socket.addEventListener("error", (error) => {
    console.error("WebSocket error:", error);
  });
  
  return socket;
}

// API endpoint helpers
export const API = {
  // Setup endpoints
  clients: () => "/v1/setup/clients",
  clientPreview: () => "/v1/setup/client-preview",
  clientApply: () => "/v1/setup/client-apply",
  discovery: () => "/v1/setup/discovery",
  import: () => "/v1/setup/import",
  verify: () => "/v1/setup/verify",
  
  // Operations endpoints
  tools: () => "/v1/tools",
  refreshTools: () => "/v1/tools/refresh",
  registerTool: () => "/v1/tools/register",
  deleteTool: (name) => `/v1/tools/${encodeURIComponent(name)}`,
  
  upstreams: () => "/v1/upstreams",
  deleteUpstream: (id) => `/v1/upstreams/${encodeURIComponent(id)}`,
  
  policies: () => "/v1/policies",
  deletePolicy: (id) => `/v1/policies/${encodeURIComponent(id)}`,
  
  audit: {
    policyDecisions: () => "/v1/audit/policy-decisions",
    toolCalls: () => "/v1/audit/tool-calls",
    events: () => "/v1/audit/events",
  },
};
