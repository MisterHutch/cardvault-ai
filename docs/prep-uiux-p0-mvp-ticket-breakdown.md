# Prep Interview Tracker — P0 MVP Ticket Breakdown

## Objective (Today)
Ship a focused P0 UI/UX improvement set that reduces cognitive load and improves conversion to action:
1. Sticky section navigation
2. Collapsible major sections
3. "Today's Brief" summary block
4. Primary "Next Step" CTA with simple rules

---

## Delivery Strategy
- Prioritize **thin vertical slices** over perfect architecture.
- Keep existing data model intact; derive UI state client-side.
- Gate polish behind "if time remains" so core P0 ships first.

---

## Epic
### EPIC-P0-PREP-UX
**Title:** Prep Tracker P0 usability uplift
**Definition of done:** User can identify priorities in <10 seconds, navigate quickly, and execute one guided next action from above the fold.

---

## Ticket 1 — Today's Brief (Top Summary Block)
**ID:** P0-001

**User story**
As a candidate preparing quickly, I need a compact summary of my interview context and top priorities so I can start with confidence.

**Scope**
- Add a new top-of-page card: `Today's Brief`
- Include:
  - Role title + company
  - Stage
  - Interview date/time (or missing-data prompt)
  - Top 3 tasks (derived or fallback defaults)
  - 60-second pitch preview (if available)
- Add explicit empty states for missing fields

**Acceptance criteria**
- Brief renders at top of page before long-form sections.
- Missing interview date shows clear prompt: `Add interview date`.
- Top tasks always shows 3 items (real values or fallback placeholders).
- No existing prep content regressions.

**Engineering notes**
- Build as isolated component (e.g., `TodaysBrief`) with prop-driven inputs.
- Fallback values should be deterministic and testable.

**Estimate**
- 2–3 hours

---

## Ticket 2 — Sticky Section Navigation
**ID:** P0-002

**User story**
As a user scanning dense prep content, I want persistent section navigation so I can jump quickly without losing context.

**Scope**
- Add sticky nav listing core sections
- Each nav item links to anchored section IDs
- Active section highlight based on scroll position
- Mobile behavior: horizontal scroll chip row or compact dropdown

**Acceptance criteria**
- Nav remains visible while scrolling on desktop.
- Clicking any nav item scrolls to correct section.
- Active state updates while scrolling.
- Mobile layout does not overlap content.

**Engineering notes**
- Use `IntersectionObserver` for active section state.
- Use smooth scrolling with reduced-motion fallback.

**Estimate**
- 2–4 hours

---

## Ticket 3 — Collapsible Section Wrappers
**ID:** P0-003

**User story**
As a user under time pressure, I want large sections collapsed by default so I can focus only on what matters now.

**Scope**
- Wrap major long-form sections in collapsible containers
- Default open:
  - Today's Brief
  - Current in-progress section
- Default collapsed:
  - Secondary deep-dive sections
- Add clear expand/collapse affordances

**Acceptance criteria**
- At least 4 major sections are collapsible.
- Default open/collapsed behavior matches spec.
- Toggle state is keyboard accessible.
- Section content is fully preserved when expanded.

**Engineering notes**
- Use semantic button headers + `aria-expanded` attributes.
- Keep DOM mounted initially to avoid heavy reflow risk.

**Estimate**
- 3–5 hours

---

## Ticket 4 — Primary "Next Step" CTA (Rule-based)
**ID:** P0-004

**User story**
As a user, I want one clear recommended action so I don't have to decide what to do next.

**Scope**
- Add a prominent primary CTA above the fold
- Add lightweight rules:
  1. If intake incomplete → `Complete Role Intake`
  2. Else if answer bank missing → `Generate 5 Tailored Answers`
  3. Else → `Start Mock Interview`
- Include secondary fallback action (less emphasized)

**Acceptance criteria**
- Exactly one primary CTA is visible at all times.
- CTA label/action changes based on current data completeness.
- CTA click routes user to intended workflow step.

**Engineering notes**
- Keep rule logic in a pure utility function for easy test coverage.

**Estimate**
- 2–3 hours

---

## Ticket 5 — QA + Regression Checklist (P0 Gate)
**ID:** P0-005

**Scope**
- Verify rendering and interaction across desktop + mobile breakpoints
- Validate anchor navigation and collapsed state behavior
- Validate CTA rule transitions against sample data states
- Smoke test existing prep generation outputs

**Acceptance criteria**
- No blocking visual regressions in core prep flow.
- No broken links/buttons introduced.
- All P0 acceptance criteria from tickets 1–4 pass.

**Estimate**
- 1.5–2 hours

---

## Execution Order (for today)
1. P0-001 Today's Brief
2. P0-002 Sticky Nav
3. P0-003 Collapsible Sections
4. P0-004 Next Step CTA
5. P0-005 QA + Ship

---

## Timebox Plan (single working session)
- 00:00–00:30: Scaffold + data mapping for Today's Brief
- 00:30–01:10: Sticky nav + anchor wiring + active state
- 01:10–02:00: Collapsible wrappers + accessibility checks
- 02:00–02:30: Next Step CTA + rules utility
- 02:30–03:00: QA checklist + final fixes

---

## Non-goals (explicitly deferred)
- Full visual redesign / design token overhaul
- Backend schema refactors
- Personalization modes and keyboard command palette
- Advanced analytics instrumentation

---

## Risk + Mitigation
- **Risk:** Active section detection jitter
  - **Mitigation:** Debounce highlight update and define clear threshold
- **Risk:** Collapsible wrappers break existing spacing
  - **Mitigation:** Start with 4 heaviest sections only, then expand
- **Risk:** CTA rule ambiguity with partial data
  - **Mitigation:** Deterministic fallback order with explicit defaults

---

## Ready-to-Track Fields (for Jira/Linear)
- Priority: P0
- Type: Feature
- Labels: `prep`, `uiux`, `mvp`, `today`
- Owner: Frontend
- QA Owner: Product/QA
- Dependencies: None (all client-side)

