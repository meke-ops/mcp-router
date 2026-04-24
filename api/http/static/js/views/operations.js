/**
 * MCP Router Dashboard - Operations View
 * Control Plane: tools, policies, upstreams, audit, events.
 */

import {
  escapeHtml,
  renderCard,
  renderButton,
  renderBadge,
  renderTable,
  renderEmptyState,
  renderLoadingState,
  renderStatusLine,
  renderEventItem,
} from "../components.js";

import {
  apiGet,
  apiPost,
  apiDelete,
} from "../api.js";

import {
  operationsStore,
  registryStore,
  authStore,
  getAuthToken,
  setGlobalStatus,
  setOperationsData,
} from "../state.js";

// ===== TAB CONFIGURATION =====

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "tools", label: "Tools" },
  { id: "policies", label: "Policies" },
  { id: "audit", label: "Audit" },
];

let activeTab = "overview";

// ===== RENDER =====

export function renderOperationsView(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = `
    <div class="section">
      <div class="action-header" style="margin-bottom: var(--space-4);">
        <div>
          <h2 style="margin-bottom: var(--space-2);">Control Plane</h2>
          <p>Manage tools, policies, and monitor operations.</p>
        </div>
        <div id="operationsStatus">
          ${renderStatusLine("", "info")}
        </div>
      </div>
      
      ${renderTabList()}
      
      <div class="tab-content" id="operationsTabContent">
        ${renderActiveTab()}
      </div>
      
      ${renderAdvancedOperations()}
      
      ${renderEventFeed()}
    </div>
  `;

  attachOperationsListeners(container);
}

function renderTabList() {
  return `
    <div class="tab-list">
      ${TABS.map((tab) => `
        <button 
          class="tab-btn ${tab.id === activeTab ? "active" : ""}" 
          data-tab="${tab.id}"
        >
          ${escapeHtml(tab.label)}
        </button>
      `).join("")}
    </div>
  `;
}

function renderActiveTab() {
  switch (activeTab) {
    case "overview":
      return renderOverviewTab();
    case "tools":
      return renderToolsTab();
    case "policies":
      return renderPoliciesTab();
    case "audit":
      return renderAuditTab();
    default:
      return renderEmptyState("Error", "Invalid tab", "error");
  }
}

// ===== OVERVIEW TAB =====

function renderOverviewTab() {
  const ops = operationsStore.get();
  const reg = registryStore.get();
  
  return `
    <div class="metrics-grid">
      ${renderMetricCard(
        reg.tools.length, 
        "Registered Tools", 
        "toolsMetric",
        () => { activeTab = "tools"; renderOperationsView("operationsView"); }
      )}
      ${renderMetricCard(
        ops.policies.length, 
        "Active Policies", 
        "policiesMetric",
        () => { activeTab = "policies"; renderOperationsView("operationsView"); }
      )}
      ${renderMetricCard(
        ops.toolCalls.length, 
        "Recent Calls", 
        "callsMetric",
        () => { activeTab = "audit"; renderOperationsView("operationsView"); }
      )}
      ${renderMetricCard(
        ops.events.length, 
        "Live Events", 
        "eventsMetric",
        null
      )}
    </div>
    
    <div class="grid-2" style="margin-top: var(--space-5);">
      ${renderRecentToolCalls()}
      ${renderRecentEvents()}
    </div>
  `;
}

function renderMetricCard(value, label, id, onClick) {
  const clickAttr = onClick ? ` onclick="(${onClick.toString()})()" style="cursor: pointer;"` : "";
  
  return `
    <div class="card metric-card" id="${id}"${clickAttr}>
      <div class="metric-value">${value}</div>
      <div class="metric-label">${escapeHtml(label)}</div>
    </div>
  `;
}

function renderRecentToolCalls() {
  const ops = operationsStore.get();
  const recentCalls = ops.toolCalls.slice(0, 5);
  
  return renderCard({
    title: "Recent Tool Calls",
    headerActions: renderButton({
      label: "View All",
      variant: "ghost",
      size: "sm",
      onClick: "activeTab='audit';renderOperationsView('operationsView')",
    }),
    children: recentCalls.length > 0
      ? `<div style="display: flex; flex-direction: column; gap: var(--space-3);">
          ${recentCalls.map((call) => `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: var(--space-3); background: var(--surface); border-radius: var(--radius-sm);">
              <div>
                <div style="font-weight: 500;">${escapeHtml(call.toolName)}</div>
                <div style="font-size: 0.75rem; color: var(--muted);">${escapeHtml(call.serverId)}</div>
              </div>
              <div style="text-align: right;">
                ${renderBadge(call.outcome, call.outcome === "allowed" ? "success" : "danger")}
                <div style="font-size: 0.75rem; color: var(--muted); margin-top: var(--space-1);">
                  ${new Date(call.timestamp).toLocaleTimeString()}
                </div>
              </div>
            </div>
          `).join("")}
        </div>`
      : `<p style="color: var(--muted);">No recent tool calls.</p>`,
  });
}

function renderRecentEvents() {
  const ops = operationsStore.get();
  const recentEvents = ops.events.slice(-5).reverse();
  
  return renderCard({
    title: "Recent Events",
    children: recentEvents.length > 0
      ? `<div style="display: flex; flex-direction: column; gap: var(--space-3);">
          ${recentEvents.map((event) => `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: var(--space-3); background: var(--surface); border-radius: var(--radius-sm);">
              <div>
                <div style="font-weight: 500;">${escapeHtml(event.eventType)}</div>
                <div style="font-size: 0.75rem; color: var(--muted);">${escapeHtml(event.toolName || event.rule || "-")}</div>
              </div>
              <div style="font-size: 0.75rem; color: var(--muted);">
                ${new Date(event.timestamp).toLocaleTimeString()}
              </div>
            </div>
          `).join("")}
        </div>`
      : `<p style="color: var(--muted);">No recent events.</p>`,
  });
}

// ===== TOOLS TAB =====

function renderToolsTab() {
  const reg = registryStore.get();
  
  const headers = ["Name", "Server", "Version", "Description"];
  const rows = reg.tools.map((tool) => [
    escapeHtml(tool.name),
    escapeHtml(tool.serverId),
    escapeHtml(tool.version || "-"),
    escapeHtml(tool.description || "-"),
  ]);

  return `
    <div class="section">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4);">
        <h3>Tool Registry</h3>
        ${renderButton({
          label: "Refresh Tools",
          variant: "secondary",
          size: "sm",
          id: "refreshToolsBtn",
        })}
      </div>
      
      ${renderTable({ headers, rows })}
    </div>
  `;
}

// ===== POLICIES TAB =====

function renderPoliciesTab() {
  const ops = operationsStore.get();
  
  const headers = ["Rule", "Effect", "Priority", "Targets"];
  const rows = ops.policies.map((policy) => [
    escapeHtml(policy.rule),
    renderBadge(policy.effect, policy.effect === "allow" ? "success" : "danger"),
    escapeHtml(String(policy.priority)),
    escapeHtml(policy.targets || "*"),
  ]);

  return `
    <div class="section">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4);">
        <h3>Policy Rules</h3>
        ${renderButton({
          label: "Refresh Policies",
          variant: "secondary",
          size: "sm",
          id: "refreshPoliciesBtn",
        })}
      </div>
      
      ${renderTable({ headers, rows })}
    </div>
  `;
}

// ===== AUDIT TAB =====

function renderAuditTab() {
  const ops = operationsStore.get();
  
  const toolCallsHeaders = ["Time", "Tool", "Server", "Outcome", "Status"];
  const toolCallsRows = ops.toolCalls.map((call) => [
    new Date(call.timestamp).toLocaleString(),
    escapeHtml(call.toolName),
    escapeHtml(call.serverId),
    renderBadge(call.outcome, call.outcome === "allowed" ? "success" : "danger"),
    escapeHtml(call.status || "-"),
  ]);

  const eventsHeaders = ["Time", "Type", "Rule/Tool", "Details"];
  const eventsRows = ops.events.map((event) => [
    new Date(event.timestamp).toLocaleString(),
    renderBadge(event.eventType, "accent"),
    escapeHtml(event.toolName || event.rule || "-"),
    `<details style="font-size: 0.75rem;">
      <summary>Details</summary>
      <pre style="margin-top: var(--space-2); white-space: pre-wrap;">${escapeHtml(JSON.stringify(event, null, 2))}</pre>
    </details>`,
  ]);

  return `
    <div class="section">
      <h3 style="margin-bottom: var(--space-4);">Audit Log</h3>
      
      <div class="section">
        <h4 style="margin-bottom: var(--space-3);">Tool Calls</h4>
        ${renderTable({ headers: toolCallsHeaders, rows: toolCallsRows })}
      </div>
      
      <div class="section">
        <h4 style="margin-bottom: var(--space-3);">Events</h4>
        ${renderTable({ headers: eventsHeaders, rows: eventsRows })}
      </div>
    </div>
  `;
}

// ===== ADVANCED OPERATIONS =====

function renderAdvancedOperations() {
  return `
    <div class="advanced-panel" id="advancedPanel">
      <div class="advanced-panel-header" id="advancedPanelHeader">
        <div>
          <h3 style="font-size: 1.125rem;">Advanced Operations</h3>
          <p style="font-size: 0.875rem; margin-top: var(--space-1);">Register policies, upstreams, and tools manually.</p>
        </div>
        <div style="display: flex; align-items: center; gap: var(--space-2);">
          <span class="label" id="advancedPanelLabel">Show</span>
          <svg class="toggle-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" style="transition: transform 200ms ease;">
            <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
      </div>
      
      <div class="advanced-panel-body" id="advancedPanelBody">
        <div class="grid-3" style="gap: var(--space-5);">
          ${renderPolicyForm()}
          ${renderUpstreamForm()}
          ${renderToolForm()}
        </div>
      </div>
    </div>
  `;
}

function renderPolicyForm() {
  return `
    <div class="card">
      <div class="card-header">
        <h4 class="card-title">Register Policy</h4>
      </div>
      
      <form id="policyForm" style="display: flex; flex-direction: column; gap: var(--space-4);">
        <div class="form-group">
          <label class="form-label">Rule Name *</label>
          <input type="text" name="rule" placeholder="allow_calculator" required />
        </div>
        
        <div class="form-group">
          <label class="form-label">Effect</label>
          <select name="effect">
            <option value="allow">Allow</option>
            <option value="deny">Deny</option>
          </select>
        </div>
        
        <div class="form-group">
          <label class="form-label">Priority</label>
          <input type="number" name="priority" value="0" />
        </div>
        
        <div class="form-group">
          <label class="form-label">Targets (comma-separated)</label>
          <input type="text" name="targets" placeholder="tool:calculator, server:math_*" />
        </div>
        
        <div class="form-group">
          <label class="form-label">Obligations (JSON)</label>
          <textarea name="obligations" rows="3" placeholder='{"require_approval": true}'></textarea>
        </div>
        
        <div>
          ${renderButton({
            label: "Register Policy",
            variant: "primary",
            type: "submit",
          })}
        </div>
        
        <div id="policyFormStatus"></div>
      </form>
    </div>
  `;
}

function renderUpstreamForm() {
  return `
    <div class="card">
      <div class="card-header">
        <h4 class="card-title">Register Upstream</h4>
      </div>
      
      <form id="upstreamForm" style="display: flex; flex-direction: column; gap: var(--space-4);">
        <div class="form-group">
          <label class="form-label">Server ID *</label>
          <input type="text" name="serverId" placeholder="math-server" required />
        </div>
        
        <div class="form-group">
          <label class="form-label">Transport</label>
          <select name="transport">
            <option value="stdio">stdio</option>
            <option value="streamable_http">streamable_http</option>
          </select>
        </div>
        
        <div class="form-group">
          <label class="form-label">URL (for HTTP)</label>
          <input type="text" name="url" placeholder="http://localhost:3000" />
        </div>
        
        <div class="form-group">
          <label class="form-label">Command (for stdio)</label>
          <input type="text" name="command" placeholder="npx" />
        </div>
        
        <div class="form-group">
          <label class="form-label">Args (comma-separated)</label>
          <input type="text" name="args" placeholder="-y, @modelcontextprotocol/server-math" />
        </div>
        
        <div>
          ${renderButton({
            label: "Register Upstream",
            variant: "primary",
            type: "submit",
          })}
        </div>
        
        <div id="upstreamFormStatus"></div>
      </form>
    </div>
  `;
}

function renderToolForm() {
  return `
    <div class="card">
      <div class="card-header">
        <h4 class="card-title">Register Tool</h4>
      </div>
      
      <form id="toolForm" style="display: flex; flex-direction: column; gap: var(--space-4);">
        <div class="form-group">
          <label class="form-label">Tool Name *</label>
          <input type="text" name="toolName" placeholder="calculate" required />
        </div>
        
        <div class="form-group">
          <label class="form-label">Server ID *</label>
          <input type="text" name="serverId" placeholder="math-server" required />
        </div>
        
        <div class="form-group">
          <label class="form-label">Version</label>
          <input type="text" name="version" placeholder="1.0.0" />
        </div>
        
        <div class="form-group">
          <label class="form-label">Description</label>
          <input type="text" name="description" placeholder="Performs mathematical calculations" />
        </div>
        
        <div class="form-group">
          <label class="form-label">Input Schema (JSON)</label>
          <textarea name="inputSchema" rows="3" placeholder='{"type": "object", "properties": {}}'></textarea>
        </div>
        
        <div>
          ${renderButton({
            label: "Register Tool",
            variant: "primary",
            type: "submit",
          })}
        </div>
        
        <div id="toolFormStatus"></div>
      </form>
    </div>
  `;
}

// ===== EVENT FEED =====

function renderEventFeed() {
  const ops = operationsStore.get();
  const recentEvents = ops.events.slice(-10).reverse();

  return `
    <div class="section" style="margin-top: var(--space-6);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4);">
        <h3>Live Event Feed</h3>
        ${renderButton({
          label: "Clear",
          variant: "ghost",
          size: "sm",
          id: "clearEventsBtn",
        })}
      </div>
      
      <div class="event-feed" id="eventFeed">
        ${recentEvents.length > 0
          ? recentEvents.map((event) => renderEventItem(
              event.eventType,
              event.timestamp,
              event
            )).join("")
          : `<p style="color: var(--muted);">No events yet.</p>`
        }
      </div>
    </div>
  `;
}

// ===== EVENT LISTENERS =====

function attachOperationsListeners(container) {
  // Tab switching
  container.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeTab = btn.dataset.tab;
      renderOperationsView("operationsView");
    });
  });

  // Advanced panel toggle
  const panelHeader = container.querySelector("#advancedPanelHeader");
  if (panelHeader) {
    panelHeader.addEventListener("click", () => {
      const panel = container.querySelector("#advancedPanel");
      const label = container.querySelector("#advancedPanelLabel");
      panel.classList.toggle("open");
      label.textContent = panel.classList.contains("open") ? "Hide" : "Show";
    });
  }

  // Form submissions
  const policyForm = container.querySelector("#policyForm");
  if (policyForm) {
    policyForm.addEventListener("submit", (e) => {
      e.preventDefault();
      handlePolicySubmit(new FormData(policyForm));
    });
  }

  const upstreamForm = container.querySelector("#upstreamForm");
  if (upstreamForm) {
    upstreamForm.addEventListener("submit", (e) => {
      e.preventDefault();
      handleUpstreamSubmit(new FormData(upstreamForm));
    });
  }

  const toolForm = container.querySelector("#toolForm");
  if (toolForm) {
    toolForm.addEventListener("submit", (e) => {
      e.preventDefault();
      handleToolSubmit(new FormData(toolForm));
    });
  }

  // Refresh buttons
  const refreshToolsBtn = container.querySelector("#refreshToolsBtn");
  if (refreshToolsBtn) {
    refreshToolsBtn.addEventListener("click", () => handleRefreshData("tools"));
  }

  const refreshPoliciesBtn = container.querySelector("#refreshPoliciesBtn");
  if (refreshPoliciesBtn) {
    refreshPoliciesBtn.addEventListener("click", () => handleRefreshData("policies"));
  }

  // Clear events
  const clearEventsBtn = container.querySelector("#clearEventsBtn");
  if (clearEventsBtn) {
    clearEventsBtn.addEventListener("click", () => {
      operationsStore.set({ events: [] });
      renderOperationsView("operationsView");
    });
  }
}

// ===== HANDLERS =====

async function handlePolicySubmit(formData) {
  const token = getAuthToken();
  
  const payload = {
    rule: formData.get("rule"),
    effect: formData.get("effect"),
    priority: parseInt(formData.get("priority"), 10) || 0,
    targets: formData.get("targets"),
    obligations: formData.get("obligations") ? JSON.parse(formData.get("obligations")) : null,
  };

  try {
    setGlobalStatus("loading", "Registering policy...");
    await apiPost("/v1/policies", token, payload);
    
    await refreshOperationsData();
    setGlobalStatus("ready", `Policy "${payload.rule}" registered.`);
    
    // Reset form
    document.getElementById("policyForm").reset();
  } catch (error) {
    setGlobalStatus("error", `Policy registration failed: ${error.message}`);
    const statusEl = document.getElementById("policyFormStatus");
    if (statusEl) {
      statusEl.innerHTML = renderStatusLine(error.message, "error");
    }
  }
}

async function handleUpstreamSubmit(formData) {
  const token = getAuthToken();
  
  const payload = {
    serverId: formData.get("serverId"),
    transport: formData.get("transport"),
    url: formData.get("url") || null,
    command: formData.get("command") || null,
    args: formData.get("args") ? formData.get("args").split(",").map((a) => a.trim()).filter(Boolean) : null,
  };

  try {
    setGlobalStatus("loading", "Registering upstream...");
    await apiPost("/v1/upstreams", token, payload);
    
    await refreshRegistryData();
    setGlobalStatus("ready", `Upstream "${payload.serverId}" registered.`);
    
    document.getElementById("upstreamForm").reset();
  } catch (error) {
    setGlobalStatus("error", `Upstream registration failed: ${error.message}`);
    const statusEl = document.getElementById("upstreamFormStatus");
    if (statusEl) {
      statusEl.innerHTML = renderStatusLine(error.message, "error");
    }
  }
}

async function handleToolSubmit(formData) {
  const token = getAuthToken();
  
  const payload = {
    toolName: formData.get("toolName"),
    serverId: formData.get("serverId"),
    version: formData.get("version") || "0.1.0",
    description: formData.get("description") || "",
    inputSchema: formData.get("inputSchema") ? JSON.parse(formData.get("inputSchema")) : {},
  };

  try {
    setGlobalStatus("loading", "Registering tool...");
    await apiPost("/v1/tools/register", token, payload);
    
    await refreshRegistryData();
    setGlobalStatus("ready", `Tool "${payload.toolName}" registered.`);
    
    document.getElementById("toolForm").reset();
  } catch (error) {
    setGlobalStatus("error", `Tool registration failed: ${error.message}`);
    const statusEl = document.getElementById("toolFormStatus");
    if (statusEl) {
      statusEl.innerHTML = renderStatusLine(error.message, "error");
    }
  }
}

async function handleRefreshData(type) {
  const token = getAuthToken();
  
  try {
    setGlobalStatus("loading", `Refreshing ${type}...`);
    
    if (type === "tools") {
      const response = await apiGet("/v1/tools", token);
      registryStore.set({ tools: response.items || [] });
    } else if (type === "policies") {
      const response = await apiGet("/v1/policies", token);
      operationsStore.set({ policies: response.items || [] });
    }
    
    setGlobalStatus("ready", `${type} refreshed.`);
    renderOperationsView("operationsView");
  } catch (error) {
    setGlobalStatus("error", `Refresh failed: ${error.message}`);
  }
}

async function refreshOperationsData() {
  const token = getAuthToken();
  
  try {
    const [policies, toolCalls, events] = await Promise.all([
      apiGet("/v1/policies", token),
      apiGet("/v1/audit/tool-calls", token),
      apiGet("/v1/audit/events", token),
    ]);
    
    operationsStore.set({
      policies: policies.items || [],
      toolCalls: toolCalls.items || [],
      events: events.items || [],
    });
  } catch (error) {
    console.error("Refresh operations failed:", error);
  }
}

async function refreshRegistryData() {
  const token = getAuthToken();
  
  try {
    const [tools, upstreams] = await Promise.all([
      apiGet("/v1/tools", token),
      apiGet("/v1/upstreams", token),
    ]);
    
    registryStore.set({
      tools: tools.items || [],
      upstreams: upstreams.items || [],
    });
  } catch (error) {
    console.error("Refresh registry failed:", error);
  }
}

// Subscribe to store changes
operationsStore.subscribe(() => {
  const container = document.getElementById("operationsView");
  if (container) {
    renderOperationsView("operationsView");
  }
});

registryStore.subscribe(() => {
  const container = document.getElementById("operationsView");
  if (container) {
    renderOperationsView("operationsView");
  }
});
