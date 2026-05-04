# Prep Tracker / Job Hunter Build Progress

## Status Snapshot (Updated)

**Current Phase:** Phase 1 — Design Foundation + UI Refactor (IN PROGRESS)

**Overall Progress:** ~25%

**Current Focus:**
- Minimal UI enforcement (Option A)
- Global design system applied
- Preparing component-level refactor

**Last updated:** 2026-05-04

---

## Phase Breakdown

### ✅ Phase 0: Strategy + Architecture (COMPLETE)
- [x] Product direction defined (minimal, action-oriented)
- [x] UI structure defined
- [x] Component architecture defined
- [x] Backend architecture selected
- [x] Tech stack locked (Clerk, Postgres, Blob, Trigger.dev)
- [x] Refactor decision made (no patching)

---

### 🔄 Phase 1: Design Foundation + UI Refactor (IN PROGRESS)

#### Completed
- [x] Minimal UI layout defined
- [x] Component structure documented
- [x] Feature spec simplified (v2)
- [x] Global design system (`global.css`) created

#### In Progress
- [ ] Locate source repo for production app
- [ ] Create backup branch
- [ ] Apply global styles
- [ ] Implement JobHunterShell
- [ ] Implement PrepWorkspace
- [ ] Replace existing dashboard

#### Not Started
- [ ] Move noisy features into More Tools
- [ ] Implement Next Step CTA logic
- [ ] Normalize all UI to card system

---

### ⏳ Phase 2: Data + Persistence (NOT STARTED)
- [ ] Setup Neon Postgres
- [ ] Add Drizzle ORM
- [ ] Create schema
- [ ] Wire opportunity + prep data

---

### ⏳ Phase 3: Auth (NOT STARTED)
- [ ] Integrate Clerk
- [ ] Protect routes
- [ ] Attach user data

---

### ⏳ Phase 4: File Storage (NOT STARTED)
- [ ] Add Vercel Blob (private)
- [ ] Resume upload flow

---

### ⏳ Phase 5: Background Jobs (NOT STARTED)
- [ ] Add Trigger.dev
- [ ] Implement answer generation

---

## Feature Spec v2 (Aligned)

### Core Product: Prep Workspace

1. Active Opportunity
- Minimal job context

2. Today’s Brief
- Role, stage, date
- Top 3 tasks
- Pitch preview

3. Next Step Engine
- Single CTA logic-driven

4. Prep Brief
- Summary + positioning

5. Answer Bank
- Max 5 answers

6. Follow-Up Draft
- Only if exists

7. More Tools
- Hidden advanced features

---

## Product Principles

- One clear next action
- No clutter
- Progressive disclosure
- Action > analysis

---

## Risks / Blockers

- ❗ Source repo not identified
- ❗ Cannot implement until repo found
- ⚠️ Unknown data storage

---

## Immediate Next Actions

1. Locate repo
2. Backup branch
3. Start UI refactor

---

## Phase 1 Definition of Done

- Minimal UI live
- One CTA visible
- Clean layout
- No dashboard clutter

---

## Notes

We are transitioning from:
Feature-heavy prototype

To:
Clean, structured product foundation
