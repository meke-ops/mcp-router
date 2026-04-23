# Dashboard Phase 1 Neobrutalist Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the bundled dashboard so the first-load experience is clearer, more action-oriented, and closer to the approved Neobrutalist UX direction.

**Architecture:** Keep the current FastAPI route and single-file dashboard delivery model, but reshape the HTML structure, CSS tokens, and small parts of the existing browser logic to promote a top utility bar, an action header, a guided setup rail, and a more secondary treatment for advanced operations. Lock the public-facing structure with route-level HTML tests instead of introducing a frontend build step.

**Tech Stack:** FastAPI, static HTML/CSS/vanilla JavaScript, pytest

---

### Task 1: Lock the new dashboard shell in tests

**Files:**
- Modify: `tests/test_control_plane.py`
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dashboard_page_renders_phase1_setup_shell(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Set up your MCP Router" in response.text
    assert "Guided setup" in response.text
    assert "Control Plane" in response.text
    assert 'id="utilityBar"' in response.text
    assert 'id="advancedOpsPanel"' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_control_plane.py::test_dashboard_page_renders_phase1_setup_shell -v`
Expected: FAIL because the current dashboard still renders the old hero and lacks the new utility/setup shell markers.

- [ ] **Step 3: Keep the existing smoke assertion aligned**

```python
def test_dashboard_page_renders(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Set up your MCP Router" in response.text
    assert "/v1/events/ws" in response.text
```

- [ ] **Step 4: Run the focused dashboard tests**

Run: `pytest tests/test_control_plane.py -k dashboard -v`
Expected: one or more FAIL results until the HTML refactor lands.

- [ ] **Step 5: Commit**

```bash
git add tests/test_control_plane.py
git commit -m "test: lock dashboard phase 1 shell"
```

### Task 2: Refactor the dashboard structure for Phase 1 onboarding

**Files:**
- Modify: `api/http/static/dashboard.html`
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Replace the landing-style hero with a utility bar and action header**

```html
<section class="utility-bar" id="utilityBar">
  <div class="utility-pill" id="routerUrlBadge"></div>
  <div class="utility-pill" id="authModeChip"></div>
  <div class="utility-pill" id="socketStatus"></div>
  <button class="button-secondary" id="reloadAllButton">Reload Dashboard</button>
</section>

<section class="action-header">
  <div>
    <p class="kicker">MCP Router dashboard</p>
    <h1>Set up your MCP Router</h1>
    <p class="hero-copy">Connect a client, verify the session, then move into server imports and control-plane work.</p>
  </div>
  <div class="hero-actions">
    <button class="button-primary" id="startSetupButton">Start setup</button>
    <button class="button-secondary" id="jumpToOperationsButton">View Control Plane</button>
  </div>
</section>
```

- [ ] **Step 2: Turn the connect tab into a guided setup rail**

```html
<section class="guided-shell">
  <div class="guided-rail">
    <article class="step-card is-active">
      <span class="step-index">01</span>
      <h3>Choose client</h3>
    </article>
    <article class="step-card">
      <span class="step-index">02</span>
      <h3>Review path and auth</h3>
    </article>
    <article class="step-card">
      <span class="step-index">03</span>
      <h3>Apply and verify</h3>
    </article>
  </div>
</section>
```

- [ ] **Step 3: Move session/auth into a compact access strip and context card**

```html
<section class="access-strip">
  <label>
    Dashboard Bearer Token
    <input id="dashboardTokenInput" type="password" />
  </label>
  <div class="toolbar">
    <button class="button-secondary" id="saveDashboardTokenButton" type="button">Save token</button>
    <button class="button-ghost" id="clearDashboardTokenButton" type="button">Clear token</button>
  </div>
</section>
```

- [ ] **Step 4: Collapse advanced forms behind a secondary panel**

```html
<section class="composer secondary-composer" id="advancedOpsPanel">
  <div class="composer-header">
    <div>
      <h3>Advanced operations</h3>
      <div class="caption">Open low-level policy, upstream, and tool forms only when you need them.</div>
    </div>
    <button class="button-ghost" id="toggleAdvancedOpsButton" type="button">Show forms</button>
  </div>
</section>
```

- [ ] **Step 5: Wire minimal JavaScript for the new navigation helpers**

```javascript
document.getElementById("startSetupButton").addEventListener("click", () => {
  state.activeTab = "connect";
  renderTabs();
  document.getElementById("clientSelect")?.focus();
});
```

- [ ] **Step 6: Run the focused dashboard test file**

Run: `pytest tests/test_control_plane.py -k dashboard -v`
Expected: PASS for dashboard shell tests.

- [ ] **Step 7: Commit**

```bash
git add api/http/static/dashboard.html tests/test_control_plane.py
git commit -m "feat: refactor dashboard phase 1 setup flow"
```

### Task 3: Verify the refactor does not break the control plane smoke surface

**Files:**
- Modify: none
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Run the full control-plane test module**

Run: `pytest tests/test_control_plane.py -v`
Expected: PASS with dashboard, setup, and control-plane coverage intact.

- [ ] **Step 2: Review scope against the design**

Checklist:

- utility bar exists
- action header replaces the old landing hero
- connect flow reads as three explicit steps
- control plane remains available
- advanced forms are visually secondary

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-04-23-dashboard-phase1-neobrutalist-refactor.md
git commit -m "docs: add dashboard phase 1 refactor plan"
```
