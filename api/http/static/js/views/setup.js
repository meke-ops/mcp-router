/**
 * MCP Router Dashboard - Setup View
 * 3-step wizard for configuring MCP client connections.
 */

import {
  escapeHtml,
  renderCard,
  renderButton,
  renderBadge,
  renderEmptyState,
  renderLoadingState,
  renderPreview,
} from "../components.js";

import {
  apiGet,
  apiPost,
  defaultMcpUrl,
} from "../api.js";

import {
  setupStore,
  registryStore,
  authStore,
  getAuthToken,
  setGlobalStatus,
} from "../state.js";

// ===== STEP CONFIGURATION =====

const STEPS = [
  { id: 1, label: "Choose Client" },
  { id: 2, label: "Review Config" },
  { id: 3, label: "Apply & Verify" },
];

// ===== RENDER FUNCTIONS =====

export function renderSetupView(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const state = setupStore.get();
  
  container.innerHTML = `
    <div class="with-sidebar">
      <div class="setup-main">
        ${renderStepIndicator(state.step)}
        <div class="step-content" id="setupStepContent">
          ${renderStepContent(state.step)}
        </div>
        <div class="step-navigation" id="stepNavigation">
          ${renderStepNavigation(state.step)}
        </div>
      </div>
      <div class="setup-sidebar">
        ${renderSetupSidebar()}
      </div>
    </div>
  `;

  attachSetupListeners(container);
}

function renderStepIndicator(currentStep) {
  return `
    <div class="step-wizard">
      <div class="step-indicator">
        ${STEPS.map((step) => {
          let status = "pending";
          if (step.id < currentStep) status = "completed";
          else if (step.id === currentStep) status = "active";
          
          return `
            <div class="step-item ${status}" data-step="${step.id}">
              <div class="step-number">${step.id < currentStep ? "✓" : step.id}</div>
              <div class="step-label">${escapeHtml(step.label)}</div>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function renderStepContent(step) {
  switch (step) {
    case 1:
      return renderStep1ClientSelection();
    case 2:
      return renderStep2ConfigPreview();
    case 3:
      return renderStep3ApplyVerify();
    default:
      return renderEmptyState("Error", "Invalid step", "error");
  }
}

function renderStepNavigation(step) {
  const state = setupStore.get();
  
  let html = '<div class="toolbar" style="margin-top: var(--space-5); padding-top: var(--space-4); border-top: 1px solid var(--line);">';
  
  if (step > 1) {
    html += renderButton({
      label: "← Previous",
      variant: "secondary",
      id: "prevStepBtn",
    });
  }
  
  if (step < 3) {
    const canProceed = step === 1 ? state.selectedClient : state.preview;
    html += renderButton({
      label: "Next →",
      variant: "primary",
      id: "nextStepBtn",
      disabled: !canProceed,
    });
  }
  
  html += "</div>";
  return html;
}

// ===== STEP 1: CLIENT SELECTION =====

function renderStep1ClientSelection() {
  const state = registryStore.get();
  const setup = setupStore.get();
  
  if (!state.clients || state.clients.length === 0) {
    return renderLoadingState("Loading supported clients...");
  }

  return `
    <div class="section">
      <h2 style="margin-bottom: var(--space-2);">Choose Your Client</h2>
      <p style="margin-bottom: var(--space-4);">Select the MCP client you want to configure.</p>
      
      <div class="client-grid" id="clientGrid">
        ${state.clients.map((client) => renderClientCard(client, setup.selectedClient)).join("")}
      </div>
    </div>
  `;
}

function renderClientCard(client, selectedId) {
  const isSelected = client.clientId === selectedId;
  const targets = client.targets || [];
  
  return `
    <div class="card client-card ${isSelected ? "selected" : ""}" data-client-id="${escapeHtml(client.clientId)}">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: var(--space-3);">
        <div>
          <h3>${escapeHtml(client.label)}</h3>
          <p style="font-size: 0.875rem; margin-top: var(--space-1);">${targets.length} target${targets.length !== 1 ? "s" : ""} available</p>
        </div>
        ${isSelected ? renderBadge("Selected", "accent") : ""}
      </div>
      
      <div class="client-meta">
        ${targets.map((target) => 
          renderBadge(
            `${target.scope} ${target.exists ? "✓" : "○"}`,
            target.exists ? "success" : "default"
          )
        ).join("")}
      </div>
      
      ${targets.length > 0 ? `
        <div style="margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--line);">
          <span class="label">Default Path</span>
          <code style="display: block; margin-top: var(--space-1); font-size: 0.75rem;">${escapeHtml(targets[0].path)}</code>
        </div>
      ` : ""}
    </div>
  `;
}

// ===== STEP 2: CONFIG PREVIEW =====

function renderStep2ConfigPreview() {
  const state = setupStore.get();
  const client = getSelectedClientData();
  
  if (!client) {
    return renderEmptyState("No Client Selected", "Please go back and select a client.", "error");
  }

  const targets = client.targets || [];
  const defaultTarget = targets[0] || {};
  
  return `
    <div class="section">
      <h2 style="margin-bottom: var(--space-2);">Review Configuration</h2>
      <p style="margin-bottom: var(--space-4);">Preview the MCP config that will be written for <strong>${escapeHtml(client.label)}</strong>.</p>
      
      <div class="form-grid" style="margin-bottom: var(--space-4);">
        <div class="form-group">
          <label class="form-label">MCP URL</label>
          <input type="text" id="mcpUrlInput" value="${escapeHtml(state.mcpUrl || defaultMcpUrl())}" />
        </div>
        
        <div class="form-group">
          <label class="form-label">Server Name</label>
          <input type="text" id="serverNameInput" value="${escapeHtml(state.serverName || "mcp-router")}" />
        </div>
      </div>
      
      <div class="form-grid" style="margin-bottom: var(--space-4);">
        <div class="form-group">
          <label class="form-label">Config Path (optional override)</label>
          <input type="text" id="configPathInput" placeholder="${escapeHtml(defaultTarget.path || "")}" />
          <span class="form-hint">Leave empty to use the default path shown above.</span>
        </div>
        
        <div class="form-group">
          <label class="form-label">Scope</label>
          <select id="scopeSelect">
            ${targets.map((target) => `
              <option value="${escapeHtml(target.scope)}" ${target.scope === "user" ? "selected" : ""}>
                ${escapeHtml(target.scope)}
              </option>
            `).join("")}
          </select>
        </div>
      </div>
      
      <div class="form-grid full" style="margin-bottom: var(--space-4);">
        <div class="form-group">
          <label class="form-label">Auth Token (optional)</label>
          <input type="password" id="tokenInput" placeholder="Bearer token for authenticated connections" />
        </div>
      </div>
      
      <div style="margin-bottom: var(--space-4);">
        ${renderButton({
          label: "Generate Preview",
          variant: "primary",
          id: "generatePreviewBtn",
        })}
      </div>
      
      <div id="previewContainer">
        ${state.preview ? renderPreviewPanel(state.preview) : ""}
      </div>
    </div>
  `;
}

function renderPreviewPanel(preview) {
  return `
    <div style="margin-top: var(--space-4);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);">
        <h3>Config Preview</h3>
        <div class="toolbar">
          ${renderButton({
            label: "Copy Config",
            variant: "secondary",
            id: "copyConfigBtn",
          })}
          ${renderButton({
            label: "Copy Path",
            variant: "ghost",
            id: "copyPathBtn",
          })}
        </div>
      </div>
      
      <div style="margin-bottom: var(--space-3);">
        ${renderBadge(preview.scope, "default")}
        ${renderBadge(preview.authMode === "bearer" ? "Authenticated" : "Open", preview.authMode === "bearer" ? "accent" : "success")}
        <span style="margin-left: var(--space-2); font-size: 0.875rem; color: var(--muted);">
          ${escapeHtml(preview.configPath)}
        </span>
      </div>
      
      ${renderPreview(preview.mergedConfigText)}
      
      ${preview.installCommand ? `
        <div style="margin-top: var(--space-3);">
          <span class="label">Install Command</span>
          <code style="display: block; margin-top: var(--space-1); padding: var(--space-2); background: var(--surface); border-radius: var(--radius-sm); font-size: 0.875rem;">
            ${escapeHtml(preview.installCommand)}
          </code>
        </div>
      ` : ""}
    </div>
  `;
}

// ===== STEP 3: APPLY & VERIFY =====

function renderStep3ApplyVerify() {
  const state = setupStore.get();
  
  if (!state.preview) {
    return renderEmptyState("No Preview", "Please go back and generate a preview first.", "error");
  }

  return `
    <div class="section">
      <h2 style="margin-bottom: var(--space-2);">Apply & Verify</h2>
      <p style="margin-bottom: var(--space-4);">Write the config and verify the router connection.</p>
      
      <div style="margin-bottom: var(--space-4);">
        ${renderButton({
          label: "Apply Configuration",
          variant: "primary",
          id: "applyConfigBtn",
          className: "btn-lg",
        })}
      </div>
      
      <div id="applyResult">
        ${state.verification ? renderVerificationResult(state.verification) : ""}
      </div>
    </div>
  `;
}

function renderVerificationResult(verification) {
  const identity = verification.identity || {};
  
  return `
    <div class="card" style="border-color: var(--success); background: rgba(40, 167, 69, 0.05);">
      <div class="card-header">
        <h3 class="card-title">Verification Successful</h3>
        ${renderBadge("Connected", "success")}
      </div>
      
      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); margin-bottom: var(--space-4);">
        <div>
          <span class="label">Session</span>
          <div style="font-weight: 500; margin-top: var(--space-1);">${escapeHtml(verification.sessionId || "N/A")}</div>
        </div>
        <div>
          <span class="label">Tools Visible</span>
          <div style="font-weight: 500; margin-top: var(--space-1);">${verification.toolCount || 0}</div>
        </div>
        <div>
          <span class="label">Auth Mode</span>
          <div style="font-weight: 500; margin-top: var(--space-1);">${escapeHtml(verification.authMode || "none")}</div>
        </div>
      </div>
      
      <div style="padding: var(--space-3); background: var(--surface); border-radius: var(--radius-sm);">
        <span class="label">Identity</span>
        <div style="margin-top: var(--space-2); font-size: 0.875rem;">
          <div><strong>Tenant:</strong> ${escapeHtml(identity.tenantId || "N/A")}</div>
          <div style="margin-top: var(--space-1);"><strong>Principal:</strong> ${escapeHtml(identity.principalId || "N/A")}</div>
          ${identity.roles && identity.roles.length > 0 ? `
            <div style="margin-top: var(--space-1);"><strong>Roles:</strong> ${identity.roles.map(escapeHtml).join(", ")}</div>
          ` : ""}
        </div>
      </div>
      
      <div style="margin-top: var(--space-4); display: flex; gap: var(--space-3);">
        ${renderButton({
          label: "Import Servers →",
          variant: "secondary",
          id: "gotoImportBtn",
        })}
        ${renderButton({
          label: "Control Panel →",
          variant: "ghost",
          id: "gotoOperationsBtn",
        })}
      </div>
    </div>
  `;
}

// ===== SIDEBAR =====

function renderSetupSidebar() {
  const state = setupStore.get();
  const client = getSelectedClientData();
  
  return `
    <div class="card setup-sidebar">
      <div class="card-header">
        <h3 class="card-title">Setup Context</h3>
      </div>
      
      <div class="info-row">
        <span class="info-label">Client</span>
        <span class="info-value">${client ? escapeHtml(client.label) : "Not selected"}</span>
      </div>
      
      <div class="info-row">
        <span class="info-label">Scope</span>
        <span class="info-value">${escapeHtml(state.scope)}</span>
      </div>
      
      <div class="info-row">
        <span class="info-label">Target Path</span>
        <span class="info-value" style="font-family: var(--font-mono); font-size: 0.75rem;">
          ${client && client.targets ? escapeHtml(client.targets[0]?.path || "N/A") : "N/A"}
        </span>
      </div>
      
      <div class="info-row">
        <span class="info-label">Auth</span>
        <span class="info-value">
          ${state.preview?.authMode === "bearer" ? renderBadge("Required", "accent") : renderBadge("Optional", "success")}
        </span>
      </div>
      
      ${state.verification ? `
        <div class="info-row">
          <span class="info-label">Status</span>
          <span class="info-value">${renderBadge("Verified", "success")}</span>
        </div>
      ` : ""}
      
      <div style="margin-top: var(--space-4); padding-top: var(--space-3); border-top: 1px solid var(--line);">
        <span class="label">Quick Actions</span>
        <div style="margin-top: var(--space-2); display: flex; flex-direction: column; gap: var(--space-2);">
          <button class="btn btn-ghost btn-sm" id="copyUrlBtn" style="justify-content: flex-start;">
            Copy MCP URL
          </button>
          <button class="btn btn-ghost btn-sm" id="copyPathBtn" style="justify-content: flex-start;">
            Copy Config Path
          </button>
        </div>
      </div>
    </div>
  `;
}

// ===== EVENT LISTENERS =====

function attachSetupListeners(container) {
  // Client card selection
  container.querySelectorAll(".client-card").forEach((card) => {
    card.addEventListener("click", () => {
      const clientId = card.dataset.clientId;
      setupStore.set({ selectedClient: clientId });
      renderSetupView("setupView");
    });
  });

  // Navigation buttons
  const prevBtn = container.querySelector("#prevStepBtn");
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      const current = setupStore.get().step;
      if (current > 1) {
        setupStore.set({ step: current - 1 });
        renderSetupView("setupView");
      }
    });
  }

  const nextBtn = container.querySelector("#nextStepBtn");
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      const current = setupStore.get().step;
      if (current < 3) {
        setupStore.set({ step: current + 1 });
        renderSetupView("setupView");
      }
    });
  }

  // Generate preview
  const previewBtn = container.querySelector("#generatePreviewBtn");
  if (previewBtn) {
    previewBtn.addEventListener("click", handleGeneratePreview);
  }

  // Apply config
  const applyBtn = container.querySelector("#applyConfigBtn");
  if (applyBtn) {
    applyBtn.addEventListener("click", handleApplyConfig);
  }

  // Copy buttons
  const copyConfigBtn = container.querySelector("#copyConfigBtn");
  if (copyConfigBtn) {
    copyConfigBtn.addEventListener("click", handleCopyConfig);
  }

  const copyPathBtn = container.querySelector("#copyPathBtn");
  if (copyPathBtn) {
    copyPathBtn.addEventListener("click", handleCopyPath);
  }

  const copyUrlBtn = container.querySelector("#copyUrlBtn");
  if (copyUrlBtn) {
    copyUrlBtn.addEventListener("click", handleCopyUrl);
  }

  // Goto buttons
  const gotoImportBtn = container.querySelector("#gotoImportBtn");
  if (gotoImportBtn) {
    gotoImportBtn.addEventListener("click", () => {
      setActiveTab("import");
    });
  }

  const gotoOperationsBtn = container.querySelector("#gotoOperationsBtn");
  if (gotoOperationsBtn) {
    gotoOperationsBtn.addEventListener("click", () => {
      setActiveTab("operations");
    });
  }
}

// ===== HANDLERS =====

async function handleGeneratePreview() {
  const state = setupStore.get();
  const token = getAuthToken();
  
  const payload = {
    clientId: state.selectedClient,
    scope: document.getElementById("scopeSelect")?.value || state.scope,
    mcpUrl: document.getElementById("mcpUrlInput")?.value || defaultMcpUrl(),
    serverName: document.getElementById("serverNameInput")?.value || "mcp-router",
    configPath: document.getElementById("configPathInput")?.value || null,
    token: document.getElementById("tokenInput")?.value || null,
  };

  try {
    setGlobalStatus("loading", "Generating config preview...");
    const response = await apiPost("/v1/setup/client-preview", token, payload);
    
    setupStore.set({
      preview: response.item,
      mcpUrl: payload.mcpUrl,
      serverName: payload.serverName,
      scope: payload.scope,
    });
    
    setGlobalStatus("ready", "Preview generated successfully.");
    renderSetupView("setupView");
  } catch (error) {
    setGlobalStatus("error", `Preview failed: ${error.message}`);
  }
}

async function handleApplyConfig() {
  const state = setupStore.get();
  const token = getAuthToken();
  
  if (!state.preview) return;

  const payload = {
    clientId: state.selectedClient,
    scope: state.scope,
    mcpUrl: state.mcpUrl,
    serverName: state.serverName,
    configPath: state.preview.configPath,
    token: state.preview.authMode === "bearer" ? state.preview.token : null,
  };

  try {
    setGlobalStatus("loading", "Applying configuration...");
    const response = await apiPost("/v1/setup/client-apply", token, payload);
    
    setupStore.set({
      preview: response.item,
      verification: response.verification,
    });
    
    setGlobalStatus("ready", "Configuration applied and verified!");
    renderSetupView("setupView");
  } catch (error) {
    setGlobalStatus("error", `Apply failed: ${error.message}`);
  }
}

async function handleCopyConfig() {
  const preview = setupStore.get().preview;
  if (!preview) return;
  
  try {
    await navigator.clipboard.writeText(preview.mergedConfigText);
    setGlobalStatus("ready", "Config copied to clipboard.");
  } catch (error) {
    setGlobalStatus("error", "Failed to copy config.");
  }
}

async function handleCopyPath() {
  const preview = setupStore.get().preview;
  if (!preview) return;
  
  try {
    await navigator.clipboard.writeText(preview.configPath);
    setGlobalStatus("ready", "Path copied to clipboard.");
  } catch (error) {
    setGlobalStatus("error", "Failed to copy path.");
  }
}

async function handleCopyUrl() {
  const state = setupStore.get();
  
  try {
    await navigator.clipboard.writeText(state.mcpUrl || defaultMcpUrl());
    setGlobalStatus("ready", "MCP URL copied to clipboard.");
  } catch (error) {
    setGlobalStatus("error", "Failed to copy URL.");
  }
}

// ===== HELPERS =====

function getSelectedClientData() {
  const { selectedClient } = setupStore.get();
  const { clients } = registryStore.get();
  return clients.find((c) => c.clientId === selectedClient) || null;
}

// Subscribe to registry changes to re-render when clients load
registryStore.subscribe(() => {
  const container = document.getElementById("setupView");
  if (container) {
    renderSetupView("setupView");
  }
});

setupStore.subscribe(() => {
  const container = document.getElementById("setupView");
  if (container) {
    renderSetupView("setupView");
  }
});
