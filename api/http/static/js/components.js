/**
 * MCP Router Dashboard - Component Renderers
 * Reusable UI component functions returning HTML strings.
 */

// HTML escaping utility
export function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// Card Component
export function renderCard(options = {}) {
  const {
    title,
    children,
    className = "",
    id = "",
    headerActions = "",
    hover = false,
  } = options;

  const hoverClass = hover ? " card-hover" : "";
  const idAttr = id ? ` id="${id}"` : "";

  return `
    <div class="card${hoverClass} ${className}"${idAttr}>
      ${title ? `
        <div class="card-header">
          <h3 class="card-title">${escapeHtml(title)}</h3>
          ${headerActions}
        </div>
      ` : ""}
      <div class="card-body">
        ${children || ""}
      </div>
    </div>
  `;
}

// Button Component
export function renderButton(options = {}) {
  const {
    label,
    onClick = "",
    variant = "primary", // primary, secondary, ghost
    size = "", // sm
    type = "button",
    id = "",
    disabled = false,
    className = "",
  } = options;

  const idAttr = id ? ` id="${id}"` : "";
  const sizeClass = size ? ` btn-${size}` : "";
  const disabledAttr = disabled ? " disabled" : "";
  const clickAttr = onClick ? ` onclick="${onClick}"` : "";

  return `
    <button type="${type}" 
            class="btn btn-${variant}${sizeClass} ${className}" 
            ${idAttr}${clickAttr}${disabledAttr}>
      ${escapeHtml(label)}
    </button>
  `;
}

// Badge Component
export function renderBadge(text, tone = "default") {
  const toneClass = tone !== "default" ? ` badge-${tone}` : "";
  return `<span class="badge${toneClass}">${escapeHtml(text)}</span>`;
}

// Table Component
export function renderTable(options = {}) {
  const { headers = [], rows = [], emptyState = null } = options;

  if (!rows || rows.length === 0) {
    return emptyState || renderEmptyState("No data", "No items to display.");
  }

  const headerHtml = headers
    .map((h) => `<th>${escapeHtml(h)}</th>`)
    .join("");

  const rowsHtml = rows
    .map(
      (row) => `
    <tr>
      ${row.map((cell) => `<td>${cell}</td>`).join("")}
    </tr>
  `
    )
    .join("");

  return `
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>${headerHtml}</tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
  `;
}

// Empty State Component
export function renderEmptyState(title, message, tone = "idle") {
  return `
    <div class="state-card state-${tone}">
      <div class="label">${escapeHtml(tone)}</div>
      <h3 style="margin-top: var(--space-3);">${escapeHtml(title)}</h3>
      <p class="card-body" style="margin-top: var(--space-2);">${escapeHtml(message)}</p>
    </div>
  `;
}

// Loading State Component
export function renderLoadingState(message = "Loading...") {
  return renderEmptyState("Loading", message, "loading");
}

// Status Line Component
export function renderStatusLine(message, tone = "info") {
  return `<div class="status-line ${tone}">${escapeHtml(message)}</div>`;
}

// State Card Component (for tables)
export function renderTableState(colspan, title, message, tone = "idle") {
  return `
    <tr>
      <td colspan="${colspan}">
        ${renderEmptyState(title, message, tone)}
      </td>
    </tr>
  `;
}

// Form Field Component
export function renderField(options = {}) {
  const {
    label,
    name,
    type = "text",
    value = "",
    placeholder = "",
    required = false,
    hint = "",
    className = "",
  } = options;

  const id = `field-${name}`;
  const requiredAttr = required ? " required" : "";
  const valueAttr = value ? ` value="${escapeHtml(value)}"` : "";
  const placeholderAttr = placeholder ? ` placeholder="${escapeHtml(placeholder)}"` : "";

  let inputHtml;
  if (type === "textarea") {
    inputHtml = `<textarea id="${id}" name="${name}" class="${className}" ${placeholderAttr}${requiredAttr}>${escapeHtml(value)}</textarea>`;
  } else if (type === "select") {
    const options = options.options || [];
    inputHtml = `
      <select id="${id}" name="${name}" class="${className}"${requiredAttr}>
        ${options.map((opt) => `<option value="${escapeHtml(opt.value)}"${opt.selected ? " selected" : ""}>${escapeHtml(opt.label)}</option>`).join("")}
      </select>
    `;
  } else {
    inputHtml = `<input type="${type}" id="${id}" name="${name}" class="${className}"${valueAttr}${placeholderAttr}${requiredAttr} />`;
  }

  return `
    <div class="form-group">
      <label for="${id}" class="form-label">${escapeHtml(label)}${required ? " *" : ""}</label>
      ${inputHtml}
      ${hint ? `<span class="form-hint">${escapeHtml(hint)}</span>` : ""}
    </div>
  `;
}

// Checkbox Component
export function renderCheckbox(options = {}) {
  const { label, name, checked = false, value = "", id = "" } = options;
  const checkboxId = id || `checkbox-${name}`;
  const checkedAttr = checked ? " checked" : "";
  const valueAttr = value ? ` value="${escapeHtml(value)}"` : "";

  return `
    <label class="checkbox-row" for="${checkboxId}">
      <input type="checkbox" id="${checkboxId}" name="${name}"${valueAttr}${checkedAttr} />
      <span>${escapeHtml(label)}</span>
    </label>
  `;
}

// Toolbar Component
export function renderToolbar(buttons = []) {
  const buttonsHtml = buttons.map((btn) => renderButton(btn)).join("");
  return `<div class="toolbar">${buttonsHtml}</div>`;
}

// Metric Card Component
export function renderMetricCard(value, label, id = "") {
  const idAttr = id ? ` id="${id}"` : "";
  return `
    <div class="card metric-card"${idAttr}>
      <div class="metric-value">${escapeHtml(String(value))}</div>
      <div class="metric-label">${escapeHtml(label)}</div>
    </div>
  `;
}

// Preview Shell Component (for code/config display)
export function renderPreview(content, language = "") {
  return `
    <div class="preview-shell">
      <pre><code>${escapeHtml(content)}</code></pre>
    </div>
  `;
}

// Event Item Component
export function renderEventItem(eventType, timestamp, detail) {
  return `
    <div class="event-item">
      <div class="event-meta">
        <span class="event-type">${escapeHtml(eventType)}</span>
        <span class="badge">${new Date(timestamp).toLocaleTimeString()}</span>
      </div>
      <pre style="margin-top: var(--space-2); font-size: 0.75rem;">${escapeHtml(JSON.stringify(detail, null, 2))}</pre>
    </div>
  `;
}
