# Dashboard Phase 3 Polish And State System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the dashboard refactor by standardizing motion, loading/empty/error states, and global feedback language across the existing UI.

**Architecture:** Keep the single-file dashboard approach, but add a small state-rendering layer in JavaScript plus a compact global status banner in the HTML shell. Use CSS variables and a few shared animation keyframes to make page entry and panel transitions feel intentional without changing backend behavior or introducing a build step.

**Tech Stack:** FastAPI, static HTML/CSS/vanilla JavaScript, pytest

---

### Task 1: Lock the Phase 3 shell in tests

**Files:**
- Modify: `tests/test_control_plane.py`
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dashboard_page_renders_phase3_state_system(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert 'id="globalStatusBanner"' in response.text
    assert "function renderStateMessage(" in response.text
    assert "@keyframes dashboard-float-in" in response.text
    assert "@media (prefers-reduced-motion: reduce)" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_control_plane.py::test_dashboard_page_renders_phase3_state_system -v`
Expected: FAIL because the current dashboard shell does not yet contain the new state-system and motion markers.

- [ ] **Step 3: Run the dashboard-only slice**

Run: `./.venv/bin/python -m pytest tests/test_control_plane.py -k dashboard -v`
Expected: at least one FAIL until the Phase 3 refactor lands.

- [ ] **Step 4: Commit**

```bash
git add tests/test_control_plane.py
git commit -m "test: lock dashboard phase 3 polish markers"
```

### Task 2: Add the global status banner and motion tokens

**Files:**
- Modify: `api/http/static/dashboard.html`
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Add a global status banner near the top shell**

```html
<section class="global-status-banner status-tone-info" id="globalStatusBanner">
  <div class="mini-label">Dashboard status</div>
  <p id="globalStatusMessage">Loading dashboard surfaces...</p>
</section>
```

- [ ] **Step 2: Add motion tokens and shared keyframes**

```css
@keyframes dashboard-float-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 3: Add reduced-motion fallback**

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation: none !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 4: Run the focused shell test**

Run: `./.venv/bin/python -m pytest tests/test_control_plane.py::test_dashboard_page_renders_phase3_state_system -v`
Expected: PASS once the shell markers exist.

- [ ] **Step 5: Commit**

```bash
git add api/http/static/dashboard.html tests/test_control_plane.py
git commit -m "feat: add dashboard phase 3 motion shell"
```

### Task 3: Unify loading, empty, and error states under shared helpers

**Files:**
- Modify: `api/http/static/dashboard.html`
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Add shared render helpers**

```javascript
function renderStateMessage(tone, title, body) {
  return `<article class="state-card state-${tone}">...</article>`;
}
```

- [ ] **Step 2: Use those helpers for preview, verification, candidates, upstreams, and events**

```javascript
if (!state.latestPreview) {
  meta.innerHTML = renderStateMessage("idle", "Preview waiting", "Generate a preview to inspect the config.");
}
```

- [ ] **Step 3: Wire global status messaging into load and action flows**

```javascript
setGlobalStatus("loading", "Loading dashboard surfaces...");
setGlobalStatus("ready", "Dashboard ready for setup.");
setGlobalStatus("error", `Initial load failed: ${String(error)}`);
```

- [ ] **Step 4: Run the full control-plane test module**

Run: `./.venv/bin/python -m pytest tests/test_control_plane.py -v`
Expected: PASS with all dashboard tests green.

- [ ] **Step 5: Commit**

```bash
git add api/http/static/dashboard.html tests/test_control_plane.py docs/superpowers/plans/2026-04-23-dashboard-phase3-polish-and-state-system.md
git commit -m "feat: finish dashboard phase 3 polish"
```
