# Prep Tracker P0 Execution Runbook (Multi-Session)

**Purpose:** Turn PRD + ticket plan into execution-ready work that can be completed in focused sessions with clear handoff.

## 1) Session Cadence and Handoff Rules
- Work in 60–90 minute build blocks.
- End each block with:
  1. What shipped
  2. What is blocked
  3. Next file/component to touch
  4. QA status delta
- Never start next ticket until current ticket has acceptance criteria checkmarked.

---

## 2) Ticket Implementation Checklist

## P0-001 Today’s Brief
### Build steps
- [ ] Create top summary container component.
- [ ] Map fields: role, company, stage, interview date/time.
- [ ] Add top 3 tasks renderer with deterministic fallback values.
- [ ] Add 60-second pitch preview slot.
- [ ] Add explicit empty states (missing interview date, missing pitch).

### QA steps
- [ ] Renders above all long-form sections.
- [ ] Missing date prompt visible.
- [ ] Exactly 3 tasks always shown.
- [ ] No visual overlap at mobile breakpoints.

### Handoff note template
- `P0-001 status: <done/in-progress>. Missing: <x>. Risks: <y>.`

---

## P0-002 Sticky Section Navigation
### Build steps
- [ ] Define canonical section IDs and labels.
- [ ] Build sticky nav shell and anchor links.
- [ ] Add smooth scroll behavior.
- [ ] Add active section state using observer.
- [ ] Add mobile-safe rendering (chips row or compact menu).

### QA steps
- [ ] Nav stays visible on desktop scroll.
- [ ] Every link lands at correct anchored section.
- [ ] Active state updates correctly when scrolling.
- [ ] Mobile nav does not block content.

### Handoff note template
- `P0-002 status: <done/in-progress>. Active-state bugs: <none/list>.`

---

## P0-003 Collapsible Sections
### Build steps
- [ ] Wrap 4+ major sections in collapsible containers.
- [ ] Set default-open for priority section(s).
- [ ] Set default-collapsed for deep-dive sections.
- [ ] Add semantic toggles + accessibility attributes.
- [ ] Verify section content completeness when expanded.

### QA steps
- [ ] Toggle behavior stable across all wrapped sections.
- [ ] Keyboard toggle works.
- [ ] Accessibility state reflects UI state.
- [ ] Layout spacing remains consistent.

### Handoff note template
- `P0-003 status: <done/in-progress>. A11y checks: <pass/fail>.`

---

## P0-004 Next Step CTA
### Build steps
- [ ] Implement pure rule-evaluation utility.
- [ ] Apply deterministic rule order.
- [ ] Render one primary CTA above fold.
- [ ] Add secondary fallback action.
- [ ] Route each CTA action to proper destination.

### QA steps
- [ ] Exactly one primary CTA shown.
- [ ] CTA switches labels by data state.
- [ ] CTA routes work in all state permutations.

### Handoff note template
- `P0-004 status: <done/in-progress>. Rule conflicts: <none/list>.`

---

## P0-005 QA Gate
### QA matrix
- [ ] Desktop: brief/nav/collapse/cta all pass
- [ ] Mobile: brief/nav/collapse/cta all pass
- [ ] No broken links or dead buttons
- [ ] No regression in existing prep outputs

### Release criteria
- [ ] All P0 tickets marked done
- [ ] No blocker defects open
- [ ] Demo path executed end-to-end

---

## 3) State Matrix for CTA Logic (Implementation + QA)
| Intake Complete | Answer Bank Exists | Expected Primary CTA |
|---|---|---|
| No | No | Complete Role Intake |
| No | Yes | Complete Role Intake |
| Yes | No | Generate 5 Tailored Answers |
| Yes | Yes | Start Mock Interview |

---

## 4) Demo Script (End-to-End)
1. Open prep page and validate Today’s Brief is visible first.
2. Use sticky nav to jump between 3+ sections.
3. Collapse/expand priority and deep-dive sections.
4. Validate CTA state for at least 2 data configurations.
5. Execute CTA and confirm destination workflow opens.

---

## 5) Defect Severity Policy (P0)
- **Blocker:** Broken nav routing, missing primary CTA, inaccessible collapse interaction.
- **Major:** Wrong active section indication, incorrect CTA selection for valid state.
- **Minor:** Copy alignment, spacing inconsistency, iconography polish.

Blockers and majors must be resolved before P0 exit.

---

## 6) Session Log Template
```
Session #: 
Date:
Owner:
Completed:
In Progress:
Blocked:
Defects Raised:
Defects Resolved:
Next Step:
```

---

## 7) Cut Scope Protocol (If Behind Schedule)
1. Keep Today’s Brief + sticky nav mandatory.
2. Collapse only top 4 heaviest sections.
3. Ship CTA logic without persistence/polish.
4. Defer non-essential visual refinements.

