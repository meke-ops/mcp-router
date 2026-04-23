# Dashboard Phase 2 Import And Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the second dashboard UX pass by making the import flow more card-driven and the control-plane surface more layered and easier to scan.

**Architecture:** Keep the existing single-file dashboard architecture, but reshape the `import` and `operations` tab markup so each screen has a clear overview row, stronger section framing, and a sharper split between read-only monitoring and manual edit tools. Protect the public shell with route-level HTML tests so the visual information architecture is pinned without introducing frontend infrastructure.

**Tech Stack:** FastAPI, static HTML/CSS/vanilla JavaScript, pytest

---

### Task 1: Lock the Phase 2 shell in tests

**Files:**
- Modify: `tests/test_control_plane.py`
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dashboard_page_renders_phase2_import_and_control_plane_shell(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Import workspace servers in one pass" in response.text
    assert "Control Plane Overview" in response.text
    assert 'id="controlPlaneOverview"' in response.text
    assert 'id="importOverview"' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_control_plane.py::test_dashboard_page_renders_phase2_import_and_control_plane_shell -v`
Expected: FAIL because the current shell does not yet expose the new Phase 2 overview markers.

- [ ] **Step 3: Run the dashboard-only slice**

Run: `./.venv/bin/python -m pytest tests/test_control_plane.py -k dashboard -v`
Expected: at least one FAIL until the Phase 2 HTML refactor lands.

- [ ] **Step 4: Commit**

```bash
git add tests/test_control_plane.py
git commit -m "test: lock dashboard phase 2 shell"
```

### Task 2: Refactor the import screen into a card-first workflow

**Files:**
- Modify: `api/http/static/dashboard.html`
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Add an import overview row above the candidate list**

```html
<section class="panel" id="importOverview">
  <div class="panel-header">
    <div>
      <div class="eyebrow">Import overview</div>
      <h2>Import workspace servers in one pass</h2>
    </div>
  </div>
</section>
```

- [ ] **Step 2: Present import candidates and imported upstreams as separated cards**

```html
<section class="panel">
  <div class="candidate-grid" id="candidateGrid"></div>
</section>

<section class="panel">
  <div class="upstream-stack" id="upstreamCards"></div>
</section>
```

- [ ] **Step 3: Keep the table body for behavior compatibility only if needed**

```html
<tbody id="upstreamsTable" hidden></tbody>
```

- [ ] **Step 4: Run the focused shell test**

Run: `./.venv/bin/python -m pytest tests/test_control_plane.py::test_dashboard_page_renders_phase2_import_and_control_plane_shell -v`
Expected: PASS after the new import shell exists.

- [ ] **Step 5: Commit**

```bash
git add api/http/static/dashboard.html tests/test_control_plane.py
git commit -m "feat: redesign dashboard import flow"
```

### Task 3: Layer the control plane with an overview row and clearer separation

**Files:**
- Modify: `api/http/static/dashboard.html`
- Test: `tests/test_control_plane.py`

- [ ] **Step 1: Add a control-plane overview section**

```html
<section class="panel" id="controlPlaneOverview">
  <div class="panel-header">
    <div>
      <div class="eyebrow">Control plane overview</div>
      <h2>Control Plane Overview</h2>
    </div>
  </div>
</section>
```

- [ ] **Step 2: Push manual edit tools into a dedicated utility column**

```html
<section class="panel">
  <h2>Live Event Feed</h2>
</section>

<section class="composer secondary-composer" id="advancedOpsPanel">
  <h3>Manual Change Desk</h3>
</section>
```

- [ ] **Step 3: Render compact metric cards from existing state**

```javascript
document.getElementById("opsToolCount").textContent = String(state.tools.length);
document.getElementById("opsPolicyCount").textContent = String(state.policies.length);
document.getElementById("opsCallCount").textContent = String(state.toolCalls.length);
document.getElementById("opsEventCount").textContent = String(state.events.length);
```

- [ ] **Step 4: Run the full control-plane test module**

Run: `./.venv/bin/python -m pytest tests/test_control_plane.py -v`
Expected: PASS with dashboard, setup, import, and control-plane coverage intact.

- [ ] **Step 5: Commit**

```bash
git add api/http/static/dashboard.html tests/test_control_plane.py docs/superpowers/plans/2026-04-23-dashboard-phase2-import-control-plane.md
git commit -m "feat: finish dashboard phase 2 control plane pass"
```
