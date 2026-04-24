/**
 * MCP Router Dashboard - Import View
 * Import existing MCP servers into the router.
 */

import {
  escapeHtml,
  renderCard,
  renderButton,
  renderBadge,
  renderEmptyState,
  renderLoadingState,
  renderStatusLine,
} from "../components.js";

import {
  apiGet,
  apiPost,
} from "../api.js";

import {
  registryStore,
  authStore,
  getAuthToken,
  setGlobalStatus,
  setRegistryData,
} from "../state.js";

// ===== RENDER =====

export function renderImportView(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const state = registryStore.get();
  
  container.innerHTML = `
    <div class="section">
      <div class="action-header" style="margin-bottom: var(--space-4);">
        <div>
          <h2 style="margin-bottom: var(--space-2);">Import Existing Servers</h2>
          <p>Discover and import MCP servers from your client configurations.</p>
        </div>
        ${renderButton({
          label: "Refresh Discovery",
          variant: "secondary",
          id: "refreshDiscoveryBtn",
        })}
      </div>
      
      ${renderImportOverview(state)}
      
      <div id="candidateContainer">
        ${renderCandidates(state.candidates)}
      </div>
      
      <div class="import-actions" id="importActions" style="display: none;">
        <div>
          <span id="selectedCount">0 selected</span>
        </div>
        ${renderButton({
          label: "Import Selected",
          variant: "primary",
          id: "importSelectedBtn",
        })}
      </div>
      
      <div id="importResult" style="margin-top: var(--space-4);"></div>
    </div>
    
    ${state.upstreams.length > 0 ? renderImportedUpstreams(state.upstreams) : ""}
  `;

  attachImportListeners(container);
  updateSelectedCount();
}

function renderImportOverview(state) {
  const importable = state.candidates.filter((c) => c.importable).length;
  const total = state.candidates.length;
  const managed = state.upstreams.filter((u) => u.managedBy && u.managedBy !== "manual").length;

  return `
    <div class="metrics-grid" style="margin-bottom: var(--space-5);">
      ${renderMetricCard(total, "Candidates", "totalCandidates")}
      ${renderMetricCard(importable, "Ready to Import", "importableCandidates")}
      ${renderMetricCard(managed, "Managed Upstreams", "managedCount")}
      ${renderMetricCard(state.upstreams.length, "Total Upstreams", "totalUpstreams")}
    </div>
  `;
}

function renderCandidates(candidates) {
  if (!candidates || candidates.length === 0) {
    return renderEmptyState(
      "No Import Candidates",
      "No known MCP client configs were found in the current discovery paths. Try refreshing or add servers manually.",
      "idle"
    );
  }

  return `
    <div class="candidate-grid" id="candidateGrid">
      ${candidates.map((candidate) => renderCandidateCard(candidate)).join("")}
    </div>
  `;
}

function renderCandidateCard(candidate) {
  const isImportable = candidate.importable;
  const statusIcon = isImportable ? "●" : "○";
  const statusColor = isImportable ? "var(--success)" : "var(--warning)";
  
  return `
    <div class="card candidate-card ${isImportable ? "" : "disabled"}" style="${!isImportable ? "opacity: 0.6;" : ""}">
      <label class="checkbox-row" style="cursor: ${isImportable ? "pointer" : "not-allowed"};">
        <input 
          type="checkbox" 
          data-candidate-id="${escapeHtml(candidate.candidateId)}"
          ${isImportable ? "" : "disabled"}
          ${isImportable ? "" : "title=\"" + escapeHtml(candidate.importReason || "Not importable") + "\""}
        />
        <div style="flex: 1; min-width: 0; overflow: hidden;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-1);">
            <h3 style="font-size: 1.125rem; font-weight: 600; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(candidate.serverName)}</h3>
            <span style="color: ${statusColor}; font-size: 0.875rem; flex-shrink: 0; margin-left: var(--space-2);" title="${isImportable ? 'Ready to import' : 'Skipped'}">${statusIcon}</span>
          </div>
          
          <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: var(--muted);">
            <span>${escapeHtml(candidate.sourceLabel)} / ${escapeHtml(candidate.scope)}</span>
            <span style="text-transform: uppercase; letter-spacing: 0.05em;">${escapeHtml(candidate.transport)}</span>
          </div>
          
          ${candidate.importReason ? `
            <div style="margin-top: var(--space-2); font-size: 0.75rem; color: var(--danger); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
              ${escapeHtml(candidate.importReason)}
            </div>
          ` : ""}
        </div>
      </label>
    </div>
  `;
}

function renderImportedUpstreams(upstreams) {
  return `
    <div class="section" style="margin-top: var(--space-6);">
      <h3 style="margin-bottom: var(--space-4);">Imported Upstreams</h3>
      <div class="upstream-stack">
        ${upstreams.map((upstream) => renderUpstreamCard(upstream)).join("")}
      </div>
    </div>
  `;
}

function renderUpstreamCard(upstream) {
  return `
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: var(--space-3);">
        <div>
          <h4 style="font-size: 1rem;">${escapeHtml(upstream.serverId)}</h4>
          <div style="margin-top: var(--space-1);">
            ${renderBadge(upstream.transport)}
            ${upstream.managedBy ? renderBadge(upstream.managedBy, upstream.managedBy !== "manual" ? "success" : "default") : ""}
          </div>
        </div>
        ${renderButton({
          label: "Delete",
          variant: "ghost",
          size: "sm",
          className: "delete-upstream-btn",
          id: `delete-${upstream.serverId}`,
        })}
      </div>
      
      <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--muted); word-break: break-all;">
        ${escapeHtml(upstream.url || [upstream.command || "", ...(upstream.args || [])].join(" ").trim() || "-")}
      </div>
      
      ${upstream.originClient ? `
        <div style="margin-top: var(--space-2); font-size: 0.75rem; color: var(--muted);">
          Origin: ${escapeHtml(upstream.originClient)}
        </div>
      ` : ""}
    </div>
  `;
}

function renderImportResult(result) {
  return `
    <div class="card" style="border-color: var(--success); background: rgba(40, 167, 69, 0.05);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);">
        <h3 style="font-size: 1.125rem;">Import Complete</h3>
        ${renderBadge("Success", "success")}
      </div>
      
      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); margin-bottom: var(--space-4);">
        <div>
          <span class="label">Imported</span>
          <div style="font-weight: 500; margin-top: var(--space-1);">${result.importedCount || 0}</div>
        </div>
        <div>
          <span class="label">Updated</span>
          <div style="font-weight: 500; margin-top: var(--space-1);">${result.updatedCount || 0}</div>
        </div>
        <div>
          <span class="label">Tools</span>
          <div style="font-weight: 500; margin-top: var(--space-1);">${result.toolCount || 0}</div>
        </div>
      </div>
      
      ${result.serverIds && result.serverIds.length > 0 ? `
        <div style="margin-top: var(--space-3);">
          <span class="label">Server IDs</span>
          <div style="margin-top: var(--space-2); display: flex; flex-wrap: wrap; gap: var(--space-2);">
            ${result.serverIds.map((id) => renderBadge(id)).join("")}
          </div>
        </div>
      ` : ""}
      
      <div style="margin-top: var(--space-4);">
        ${renderButton({
          label: "Refresh Discovery",
          variant: "secondary",
          id: "refreshAfterImportBtn",
        })}
      </div>
    </div>
  `;
}

// Import metrics card
function renderMetricCard(value, label) {
  return `
    <div class="card" style="text-align: center;">
      <div style="font-size: 2rem; font-weight: 700; color: var(--accent); line-height: 1;">${value}</div>
      <div style="margin-top: var(--space-2); font-size: 0.875rem; color: var(--muted);">${label}</div>
    </div>
  `;
}

// ===== EVENT LISTENERS =====

function attachImportListeners(container) {
  // Checkbox change
  container.querySelectorAll('input[type="checkbox"][data-candidate-id]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      updateSelectedCount();
    });
  });

  // Refresh discovery
  const refreshBtn = container.querySelector("#refreshDiscoveryBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", handleRefreshDiscovery);
  }

  // Import selected
  const importBtn = container.querySelector("#importSelectedBtn");
  if (importBtn) {
    importBtn.addEventListener("click", handleImportSelected);
  }

  // Refresh after import
  const refreshAfterBtn = container.querySelector("#refreshAfterImportBtn");
  if (refreshAfterBtn) {
    refreshAfterBtn.addEventListener("click", handleRefreshDiscovery);
  }

  // Delete upstream
  container.querySelectorAll(".delete-upstream-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const serverId = btn.id.replace("delete-", "");
      handleDeleteUpstream(serverId);
    });
  });
}

// ===== HANDLERS =====

function updateSelectedCount() {
  const selected = getSelectedCandidateIds();
  const countEl = document.getElementById("selectedCount");
  const actionsEl = document.getElementById("importActions");
  
  if (countEl) {
    countEl.textContent = `${selected.length} selected`;
  }
  
  if (actionsEl) {
    actionsEl.style.display = selected.length > 0 ? "flex" : "none";
  }
}

function getSelectedCandidateIds() {
  return [...document.querySelectorAll('[data-candidate-id]:checked')]
    .map((node) => node.dataset.candidateId);
}

async function handleRefreshDiscovery() {
  try {
    setGlobalStatus("loading", "Scanning for MCP server configs...");
    const token = getAuthToken();
    const response = await apiGet("/v1/setup/discovery", token);
    
    registryStore.set({ candidates: response.items || [] });
    setGlobalStatus("ready", `Found ${response.items?.length || 0} candidates.`);
    renderImportView("importView");
  } catch (error) {
    setGlobalStatus("error", `Discovery failed: ${error.message}`);
  }
}

async function handleImportSelected() {
  const candidateIds = getSelectedCandidateIds();
  
  if (candidateIds.length === 0) {
    setGlobalStatus("error", "Select at least one candidate to import.");
    return;
  }

  try {
    setGlobalStatus("loading", `Importing ${candidateIds.length} servers...`);
    const token = getAuthToken();
    const response = await apiPost("/v1/setup/import", token, {
      candidateIds,
      refresh: true,
    });
    
    const result = response.item || {};
    
    // Refresh data
    await refreshAllData();
    
    // Show result
    const resultContainer = document.getElementById("importResult");
    if (resultContainer) {
      resultContainer.innerHTML = renderImportResult(result);
    }
    
    setGlobalStatus(
      "ready",
      `Imported ${result.importedCount}, updated ${result.updatedCount}, ${result.toolCount} tools visible.`
    );
  } catch (error) {
    setGlobalStatus("error", `Import failed: ${error.message}`);
  }
}

async function handleDeleteUpstream(serverId) {
  if (!confirm(`Delete upstream "${serverId}"?`)) return;
  
  try {
    setGlobalStatus("loading", `Deleting upstream ${serverId}...`);
    const token = getAuthToken();
    await apiPost(`/v1/upstreams/${encodeURIComponent(serverId)}`, token, null);
    
    await refreshAllData();
    setGlobalStatus("ready", `Deleted upstream ${serverId}.`);
    renderImportView("importView");
  } catch (error) {
    setGlobalStatus("error", `Delete failed: ${error.message}`);
  }
}

async function refreshAllData() {
  const token = getAuthToken();
  
  try {
    const [upstreams, tools] = await Promise.all([
      apiGet("/v1/upstreams", token),
      apiGet("/v1/tools", token),
    ]);
    
    registryStore.set({
      upstreams: upstreams.items || [],
      tools: tools.items || [],
    });
  } catch (error) {
    console.error("Refresh failed:", error);
  }
}

// Subscribe to registry changes
registryStore.subscribe(() => {
  const container = document.getElementById("importView");
  if (container) {
    renderImportView("importView");
  }
});
