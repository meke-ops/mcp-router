# MCP Router Dashboard Refactor Tasks

## Overview

This document tracks the progressive refactoring of `api/http/static/dashboard.html` from a monolithic 2600+ line file into a modular, user-friendly interface.

**Goal:** Reduce cognitive load so a new user can answer "What should I do first?" within 10-15 seconds.

---

## Phase 1: Structural Foundation

### Task 1.1: Create Directory Structure
**Status:** ✅ Completed
**Priority:** High
**Files:** New directories only

Create the following structure:
```
api/http/static/
├── index.html              # Main shell (~200 lines)
├── css/
│   ├── base.css           # CSS reset + variables
│   ├── layout.css         # Grid/flex utilities
│   ├── components.css     # Reusable UI components
│   └── views.css          # Tab-specific styles
├── js/
│   ├── api.js             # HTTP/WebSocket client
│   ├── state.js           # Centralized state management
│   ├── components.js      # UI component renderers
│   └── views/
│       ├── setup.js       # Setup flow logic
│       ├── import.js      # Import screen logic
│       └── operations.js  # Control Plane logic
```

**Success Criteria:**
- [x] All directories created
- [x] Empty placeholder files created in each directory
- [x] No changes to existing dashboard.html yet

---

### Task 1.2: Extract CSS
**Status:** ✅ Completed
**Priority:** High
**Files:** `css/base.css`, `css/layout.css`, `css/components.css`, `css/views.css`

Move all CSS from dashboard.html into modular stylesheets:
- `base.css`: CSS variables (simplified palette), reset, typography
- `layout.css`: Grid systems, flex utilities, responsive breakpoints
- `components.css`: Buttons, cards, badges, inputs, tabs
- `views.css`: Tab-pane specific layouts

**Success Criteria:**
- [x] All CSS extracted from dashboard.html
- [x] No visual regressions when stylesheets loaded
- [x] CSS variables reduced to 8 core colors
- [x] Neo-brutalist borders softened (1px instead of 3px)

---

### Task 1.3: Extract JavaScript - API Client
**Status:** ✅ Completed
**Priority:** High
**Files:** `js/api.js`

Extract all API-related functions:
- `fetchJson()`, `buildHeaders()`
- WebSocket connection logic (`connectEvents()`)
- Endpoint URLs and HTTP methods

**Success Criteria:**
- [x] All fetch/WebSocket logic in api.js
- [x] Proper error handling for network failures
- [x] Token injection handled transparently

---

### Task 1.4: Extract JavaScript - State Management
**Status:** ⬜ Not Started
**Priority:** High
**Files:** `js/state.js`

Replace monolithic state object with modular stores:
```javascript
// auth.js
const authStore = { token: null, status: 'optional' };

// setup.js  
const setupStore = {
  step: 1,
  selectedClient: null,
  preview: null,
  verification: null
};

// registry.js
const registryStore = {
  upstreams: [],
  tools: [],
  candidates: []
};

// operations.js
const operationsStore = {
  policies: [],
  toolCalls: [],
  events: []
};
```

**Success Criteria:**
- [ ] State split into domain-specific modules
- [ ] Each module has get/set/subscribe pattern
- [ ] No global `state` object remains

---

### Task 1.5: Create Component Renderer System
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `js/components.js`

Build reusable render functions:
- `renderCard(title, content, options)`
- `renderButton(label, onClick, variant)`
- `renderBadge(text, tone)`
- `renderTable(headers, rows)`
- `renderForm(fields, onSubmit)`
- `renderEmptyState(title, message)`
- `renderLoadingState(message)`

**Success Criteria:**
- [ ] All UI patterns abstracted into functions
- [ ] Consistent CSS classes applied
- [ ] No inline HTML generation in view files

---

## Phase 2: Setup Flow Redesign

### Task 2.1: Implement Step Wizard Component
**Status:** ⬜ Not Started
**Priority:** High
**Files:** `js/views/setup.js`, `css/views.css`

Create a 3-step wizard:
```
┌─────────────────────────────────────┐
│  Step 1        Step 2        Step 3 │
│ [Choose      [Review       [Apply  │
│  Client]      Config]       & Verify]
│                                     │
│ ┌─────────────────────────────┐    │
│ │ Active step content...      │    │
│ └─────────────────────────────┘    │
│                                     │
│ [Previous]              [Next]     │
└─────────────────────────────────────┘
```

**Success Criteria:**
- [ ] Step indicator renders correctly
- [ ] Only active step content visible
- [ ] Navigation buttons work (Next/Previous)
- [ ] Step validation prevents advancing

---

### Task 2.2: Step 1 - Client Selection
**Status:** ⬜ Not Started
**Priority:** High
**Files:** `js/views/setup.js`

Implement client selection step:
- Display client cards (Claude Code, Cursor, Codex, OpenCode)
- Show detected scopes (user/project) with visual indicators
- Single selection only
- Auto-advance to step 2 on selection

**Success Criteria:**
- [ ] Client cards render with correct info
- [ ] Selected state visually clear
- [ ] Scope badges show detected/undetected
- [ ] Selection triggers step advance

---

### Task 2.3: Step 2 - Config Preview
**Status:** ⬜ Not Started
**Priority:** High
**Files:** `js/views/setup.js`

Implement preview step:
- Show selected client info
- Display config path (with override option)
- Generate and show preview JSON/TOML
- "Copy Config" button
- MCP URL input (pre-filled)

**Success Criteria:**
- [ ] Preview generates on step entry
- [ ] Config format correct for selected client
- [ ] Copy button works
- [ ] URL override functional

---

### Task 2.4: Step 3 - Apply & Verify
**Status:** ⬜ Not Started
**Priority:** High
**Files:** `js/views/setup.js`

Implement apply step:
- "Apply Config" button (prominent)
- Show apply result (success/failure)
- Auto-run verification
- Display verification results:
  - Session ID
  - Tool count
  - Auth mode
  - Identity info
- "Go to Import" or "Go to Operations" CTA on success

**Success Criteria:**
- [ ] Apply button calls correct API
- [ ] Success/failure clearly shown
- [ ] Verification runs automatically
- [ ] Results displayed in readable format
- [ ] Next-step CTAs appear on success

---

### Task 2.5: Setup Context Sidebar
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `js/views/setup.js`, `css/views.css`

Create a persistent sidebar during setup:
- Selected client
- Target path
- Auth requirement
- Last verification result
- Quick copy shortcuts (URL, path)

**Success Criteria:**
- [ ] Sidebar visible during all setup steps
- [ ] Content updates based on selection
- [ ] Doesn't compete with main flow for attention
- [ ] Collapsible on mobile

---

## Phase 3: Import Screen Redesign

### Task 3.1: Simplify Import Layout
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `js/views/import.js`, `css/views.css`

Redesign import screen:
- Header: "Import Existing Servers" + one-line description
- Main area: Candidate cards with checkboxes
- Bottom: "Import Selected" button (disabled if none selected)
- Side/Bottom: Already imported upstreams (minimal)

**Success Criteria:**
- [ ] Layout follows single-purpose principle
- [ ] Candidates clearly selectable
- [ ] Import button prominent
- [ ] Already imported list doesn't dominate

---

### Task 3.2: Candidate Card Component
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `js/components.js`

Create candidate card:
- Server name (bold)
- Source client + scope
- Transport type badge
- Config path (code style)
- Importable status (green/orange badge)
- Checkbox for selection
- Skip reason if not importable

**Success Criteria:**
- [ ] All candidate info visible at glance
- [ ] Importable vs non-importable clear
- [ ] Checkbox state syncs with "Import" button
- [ ] Responsive (stacks on mobile)

---

### Task 3.3: Import Results Feedback
**Status:** ⬜ Not Started
**Priority:** Low
**Files:** `js/views/import.js`

Show post-import feedback:
- Success count
- Updated count
- Tool count discovered
- List of imported server IDs
- "Refresh Discovery" button

**Success Criteria:**
- [ ] Results displayed after import
- [ ] Clear counts shown
- [ ] Error state handled gracefully

---

## Phase 4: Control Plane Redesign

### Task 4.1: Overview Dashboard
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `js/views/operations.js`, `css/views.css`

Create overview row:
- 4 metric cards:
  - Tools count
  - Policies count
  - Recent calls count
  - Live events count
- Each card clickable (navigates to detail)
- Auto-updates via WebSocket

**Success Criteria:**
- [ ] 4 cards render with live data
- [ ] Numbers update via WebSocket
- [ ] Clickable navigation works

---

### Task 4.2: Data Tables
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `js/views/operations.js`, `js/components.js`

Implement read-only tables:
- Tool Registry: Name, Server, Version, Description
- Policies: Rule, Effect, Priority, Targets
- Tool Calls: When, Tool, Server, Outcome, Status
- Sortable columns
- Pagination (if >20 rows)

**Success Criteria:**
- [ ] All tables render correctly
- [ ] Column sorting works
- [ ] Empty states handled
- [ ] Responsive (horizontal scroll if needed)

---

### Task 4.3: Advanced Operations Accordion
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `js/views/operations.js`, `css/views.css`

Collapsible advanced section:
- Default: Collapsed
- Toggle button: "Show Advanced Operations"
- Contains 3 forms:
  - Policy registration
  - Upstream registration
  - Tool registration
- Each form has its own submit + status

**Success Criteria:**
- [ ] Section starts collapsed
- [ ] Toggle works smoothly
- [ ] Forms submit correctly
- [ ] Success/error feedback per form

---

### Task 4.4: Live Event Feed
**Status:** ⬜ Not Started
**Priority:** Low
**Files:** `js/views/operations.js`

Redesign event feed:
- Compact event items
- Type badge + timestamp
- Collapsible JSON detail
- Max 30 items, auto-scroll
- "Clear" button

**Success Criteria:**
- [ ] Events display in real-time
- [ ] Compact view doesn't dominate
- [ ] JSON detail expandable
- [ ] Auto-scroll optional

---

## Phase 5: Design System Polish

### Task 5.1: Simplify Color Palette
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `css/base.css`

Reduce to core colors:
- `--bg`: #ffffff (white)
- `--surface`: #f8f9fa (light gray)
- `--ink`: #1a1a1a (near black)
- `--muted`: #6c757d (gray)
- `--accent`: #ff7a00 (orange)
- `--success`: #28a745 (green)
- `--warning`: #ffc107 (yellow)
- `--danger`: #dc3545 (red)

**Success Criteria:**
- [ ] Only 8 core colors defined
- [ ] All components use these variables
- [ ] No inline colors in JS/HTML

---

### Task 5.2: Typography & Spacing
**Status:** ⬜ Not Started
**Priority:** Low
**Files:** `css/base.css`, `css/layout.css`

Standardize:
- Font stack: system-ui, -apple-system, sans-serif
- 4 heading sizes (h1-h4)
- Consistent spacing scale (4px, 8px, 16px, 24px, 32px)
- Line heights (1.25 for headings, 1.5 for body)

**Success Criteria:**
- [ ] Typography consistent across all views
- [ ] Spacing follows 4px grid
- [ ] No magic numbers in CSS

---

### Task 5.3: Component Hover/Focus States
**Status:** ⬜ Not Started
**Priority:** Low
**Files:** `css/components.css`

Add interaction states:
- Buttons: subtle lift on hover, focus ring
- Cards: slight shadow increase on hover
- Inputs: border color change on focus
- Links: underline animation

**Success Criteria:**
- [ ] All interactive elements have hover state
- [ ] Focus visible for keyboard navigation
- [ ] Animations subtle (<200ms)

---

## Phase 6: Testing & Validation

### Task 6.1: Cross-Browser Testing
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** All

Test in:
- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

**Success Criteria:**
- [ ] Layout consistent across browsers
- [ ] WebSocket works everywhere
- [ ] No console errors

---

### Task 6.2: Mobile Responsiveness
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** `css/layout.css`

Verify at breakpoints:
- < 576px: Single column, stacked layout
- 576-768px: Two columns where appropriate
- 768-992px: Full grid
- > 992px: Max-width container

**Success Criteria:**
- [ ] All views usable on mobile
- [ ] Tables horizontally scrollable
- [ ] Touch targets > 44px

---

### Task 6.3: Accessibility Audit
**Status:** ⬜ Not Started
**Priority:** Medium
**Files:** All

Check:
- Color contrast (WCAG AA)
- Keyboard navigation (Tab order)
- ARIA labels where needed
- Screen reader compatibility

**Success Criteria:**
- [ ] Contrast ratios meet AA
- [ ] All functionality keyboard accessible
- [ ] No ARIA violations

---

## Task Legend

- ⬜ Not Started
- 🔄 In Progress
- ✅ Completed
- ⏸️ Blocked

## Notes

- Backend API contract remains unchanged throughout
- No new dependencies added
- Vanilla JS only (no frameworks)
- Each task should be committed separately per AGENTS.md workflow rules
