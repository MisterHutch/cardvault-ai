# Product Requirements Document (PRD)
## Prep Interview Tracker — P0 MVP Usability Rollout

**Owner:** Product + Frontend  
**Date:** April 29, 2026  
**Status:** Ready for multi-session execution  
**Scope Level:** P0 MVP

---

## 1) Executive Summary
This PRD captures the agreed P0 usability rollout for the Prep Interview Tracker to reduce cognitive load and improve action conversion in interview-prep workflows. The implementation is intentionally thin-slice and client-first so it can be shipped incrementally over multiple sessions without backend schema refactors.

### P0 Outcomes
1. Users can understand interview priorities within 10 seconds.
2. Users can navigate long prep content quickly.
3. Users receive one clear recommended next action.
4. Core prep workflow remains stable with no blocking regressions.

---

## 2) Problem Statement
Current experience presents high-value data, but dense long-form layout and weak action hierarchy create friction:
- Excessive scrolling across many sections.
- Difficulty identifying what to do now.
- Important metadata (stage/date/tasks) competes with narrative content.
- No singular guided action path above the fold.

This leads to slower prep starts, lower confidence, and inconsistent session outcomes.

---

## 3) Goals and Non-Goals

### Goals (P0)
- Ship sticky section navigation.
- Ship collapsible long-form sections.
- Ship top-of-page “Today’s Brief”.
- Ship rule-based primary “Next Step” CTA.
- Preserve existing content generation and data structures.

### Non-Goals (deferred)
- Full design system overhaul.
- Backend schema redesign.
- Advanced personalization modes.
- Command palette / keyboard-first workflows.
- Deep analytics architecture.

---

## 4) Users and Core Use Cases

### Primary User
Candidate preparing for scheduled interviews under time pressure.

### Key Use Cases
1. **Rapid orientation:** “What interview is this and what matters most now?”
2. **Focused execution:** “Take me to the exact section I need.”
3. **Guided flow:** “Tell me the best next step so I can continue momentum.”

---

## 5) Product Requirements

## 5.1 Today’s Brief (P0-001)
**Requirement:** Add a concise summary block at the top of the prep page.

**Must include:**
- Role title + company
- Stage
- Interview date/time (with missing prompt)
- Top 3 tasks
- 60-second pitch preview (if present)

**Acceptance Criteria**
- Renders above long-form content.
- Missing interview date shows explicit prompt (`Add interview date`).
- Top 3 tasks always shown via real or fallback values.
- No regressions to existing downstream sections.

---

## 5.2 Sticky Section Navigation (P0-002)
**Requirement:** Persistent section navigation that supports anchored jumps and active-state context.

**Must include:**
- Core section list
- Anchor-based navigation
- Active section highlight
- Mobile-safe presentation (chips row or compact menu)

**Acceptance Criteria**
- Nav remains visible while scrolling on desktop.
- Clicking a nav item lands on the correct section.
- Active state updates with scroll position.
- Mobile layout does not obscure content.

---

## 5.3 Collapsible Section Wrappers (P0-003)
**Requirement:** Wrap major sections with accessible collapse/expand behavior.

**Must include:**
- At least 4 major sections collapsible
- Default-open high-priority content
- Default-collapsed secondary deep content
- Keyboard accessibility and clear affordance

**Acceptance Criteria**
- Collapse behavior works reliably across key sections.
- `aria-expanded` updates correctly.
- Expanded content matches pre-change content completeness.

---

## 5.4 Primary Next Step CTA (P0-004)
**Requirement:** One prominent, deterministic primary action above the fold.

**Rule order (MVP):**
1. Intake incomplete → `Complete Role Intake`
2. Intake complete + answer bank missing → `Generate 5 Tailored Answers`
3. Otherwise → `Start Mock Interview`

**Acceptance Criteria**
- Exactly one primary CTA is present.
- CTA label/action updates by data completeness state.
- CTA routes user to intended workflow target.

---

## 5.5 QA Gate (P0-005)
**Requirement:** Complete a targeted regression pass before shipping.

**Must validate:**
- Desktop + mobile rendering
- Anchor navigation + active state
- Collapse/expand behavior + accessibility states
- CTA rule transitions with sample states
- No broken actions/links in prep flow

---

## 6) UX Principles for this Rollout
- **Clarity over completeness:** show most important context first.
- **Action-first hierarchy:** one primary recommended action.
- **Progressive disclosure:** reduce initial content burden.
- **Consistency:** predictable section controls and navigation behavior.

---

## 7) Technical Constraints and Implementation Notes
- Prefer client-side derivation of completeness state.
- Avoid backend schema changes for MVP.
- Keep rule logic in pure utility functions for testability.
- Use `IntersectionObserver` for active nav highlight.
- Implement semantic collapse controls with accessibility attributes.

---

## 8) Delivery Plan Across Multiple Sessions

### Session 1 (Foundation)
- Scaffold Today’s Brief component and data mapping.
- Implement sticky nav with anchors.

### Session 2 (Interaction Layer)
- Implement collapsible wrappers across 4+ core sections.
- Add accessibility checks for collapse interactions.

### Session 3 (Guidance + Hardening)
- Implement Next Step CTA rules and routing.
- Execute QA gate and fix regressions.

### Session 4+ (If needed)
- Polish spacing/hierarchy.
- Optional persistence of collapse state.
- Minimal instrumentation for CTA and section-use tracking.

---

## 9) Milestones and Exit Criteria

### Milestone A: Orientation Shipped
- Today’s Brief live and populated/fallback-safe.
- Sticky nav functional.

### Milestone B: Focus Shipped
- Collapsible sections live with accessible interactions.

### Milestone C: Guided Action Shipped
- Next Step CTA deterministic and routed.
- QA gate completed with no blockers.

**P0 Exit Criteria**
- All four P0 features are live.
- No critical regressions in core prep flow.
- Team can demonstrate end-to-end prep journey with reduced cognitive load.

---

## 10) Risks and Mitigations
- **Active-state jitter in sticky nav** → adjust observer thresholds and update cadence.
- **Layout regressions from collapsibles** → phase rollout to heaviest sections first.
- **Ambiguous CTA states** → deterministic fallback ordering and explicit defaults.
- **Scope creep** → enforce non-goals and session exit criteria.

---

## 11) Open Decisions (to resolve during implementation)
1. Preferred mobile nav pattern (chips row vs compact menu).
2. Whether collapse state persists between sessions (P0 optional).
3. Exact visual treatment of CTA prominence within existing design language.

---

## 12) Backlog After P0 (P1 candidates)
- Confidence badges (High/Medium/Needs verification).
- Section completion indicators.
- Keyboard shortcuts and command palette.
- Expanded analytics instrumentation.
- Prep Mode variants by interview type.

---

## 13) Implementation Checklist (Quick Reference)
- [ ] Build Today’s Brief block
- [ ] Wire sticky nav + anchors + active highlight
- [ ] Add collapsible wrappers to 4+ sections
- [ ] Add primary Next Step CTA logic + routing
- [ ] Run P0 QA gate
- [ ] Ship + capture follow-up backlog

