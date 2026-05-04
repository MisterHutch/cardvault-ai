# Prep Tracker / Job Hunter Build Progress

## Status Snapshot

Current phase: Refactor planning and alignment.

Current direction:
- Option A: clean, minimal, focused UI.
- Refactor cleanly rather than layering more features onto the noisy prototype.
- Build toward a robust multi-user foundation using Clerk, Postgres, Vercel Blob, and Trigger.dev.

Last updated: 2026-05-04

---

## Product Decisions

### Accepted
- Product should be a polished personal job-search command center first, not monetization-first SaaS.
- Default UI should be calm, minimal, and action-oriented.
- Main workspace order should be:
  1. Today’s Brief
  2. Next Step CTA
  3. Prep Brief
  4. Answer Bank
  5. Follow-Up Draft
  6. More Tools collapsed
- Heavy/noisy modules should move into `More Tools` by default.
- Use Clerk for auth.
- Use Postgres for core relational app data.
- Use Drizzle ORM.
- Use Vercel Blob only for files and large artifacts, not primary app data.
- Use Trigger.dev only for async/background/AI-heavy work.
- Create a global CSS/design token layer to keep visual structure consistent.

### Rejected / Avoid
- Do not use Vercel Blob as the main database.
- Do not use Trigger.dev for basic UI state or simple saves.
- Do not keep large metric dashboards visible by default.
- Do not show multiple competing above-the-fold CTAs.

---

## Current Docs in This Branch

- `docs/prep-uiux-p0-prd.md`
- `docs/prep-uiux-p0-mvp-ticket-breakdown.md`
- `docs/prep-uiux-p0-execution-runbook.md`
- `docs/prep-ui-minimal-implementation-structure.md`
- `docs/prep-architecture-decision-record.md`
- `docs/prep-build-progress.md`

---

## Open Critical Items

1. Identify actual editable source repo for `prep.hutchgroupllc.com` / Vercel project `interview-prep-tracker`.
2. Create and document backup branch/rollback point before implementation.
3. Confirm current persistence mechanism, if any.
4. Confirm whether current prep content is hardcoded, local-only, or stored somewhere.
5. Decide whether Clerk lands before or after the first minimal UI shell refactor.

---

## Recommended Build Sequence

### Phase 0: Source + Backup
- [ ] Locate source repo for production app.
- [ ] Record current production deployment ID.
- [ ] Create backup branch from current production/source branch.
- [ ] Document rollback instructions.

### Phase 1: Design Foundation
- [ ] Add `src/styles/globals.css` or update existing global CSS.
- [ ] Add design tokens: color, spacing, radius, layout width, typography.
- [ ] Normalize base layout styles.
- [ ] Add reusable classes or Tailwind-compatible token structure.

### Phase 2: Minimal UI Shell
- [ ] Add `JobHunterShell`.
- [ ] Add `AppHeader`.
- [ ] Add `OpportunityRail`.
- [ ] Add `MobileOpportunityPicker`.
- [ ] Add `PrepWorkspace`.
- [ ] Add Today’s Brief, Next Step, Prep Brief, Answer Bank, Follow-Up Draft, More Tools sections.
- [ ] Move noisy modules into collapsed More Tools.

### Phase 3: Rule Utilities
- [ ] Add `nextStepRules.ts`.
- [ ] Add fallback content utilities.
- [ ] Add derived display helpers.
- [ ] Add domain types.

### Phase 4: Persistence Foundation
- [ ] Add Neon Postgres.
- [ ] Add Drizzle schema/migrations.
- [ ] Add users/opportunities/prep tables.
- [ ] Migrate/seed current data.

### Phase 5: Auth
- [ ] Add Clerk provider.
- [ ] Add middleware/route protection.
- [ ] Attach records to Clerk user.
- [ ] Add authenticated empty states.

### Phase 6: File Storage
- [ ] Add private Vercel Blob store.
- [ ] Add resume/document upload flow.
- [ ] Store Blob metadata in Postgres.

### Phase 7: Background Jobs
- [ ] Add Trigger.dev.
- [ ] Implement `generate-answer-bank` first.
- [ ] Store task status in Postgres.
- [ ] Add pitch/follow-up jobs after first task flow works.

---

## P0 Acceptance Criteria

- [ ] First screen shows active opportunity context, Today’s Brief, and one Next Step CTA.
- [ ] User can understand what to do next within roughly 10 seconds.
- [ ] Answer Bank shows no more than 5 answers by default.
- [ ] Heavy/secondary features are collapsed inside More Tools.
- [ ] Existing generated content remains accessible.
- [ ] Mobile view is clean and usable.
- [ ] No backend schema changes during pure UI shell pass unless necessary.
- [ ] Backup branch and preview URL are documented.

---

## Notes for Future Sessions

- Keep the UI minimal even when adding infrastructure.
- Any new feature must answer: does this help the user take the next useful job-search action faster?
- If a feature is useful but not immediately actionable, place it in `More Tools`.
- Prefer small vertical slices over broad rewrites.
- Do not merge implementation without a preview and rollback path.
