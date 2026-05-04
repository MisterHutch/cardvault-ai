# Prep Tracker Minimal UI Implementation Structure

## Purpose
This file translates the P0 usability PRD into an implementation scaffold for the actual app behind `prep.hutchgroupllc.com` / `interview-prep-tracker`.

The goal is a clean, minimal, action-oriented interface. Treat this as the component/file structure Codex should map onto the real source repo once identified.

---

## Product Direction

### Chosen direction
Option A: clean and minimal.

### Core promise
Help the user understand the active opportunity, prep focus, and next useful action within roughly 10 seconds.

### Design posture
- Calm over comprehensive
- One clear next action over many competing actions
- Progressive disclosure over dense dashboards
- Personal command center over monetized SaaS cockpit

---

## Recommended App Structure

This assumes a Next.js / React project. Adapt paths if the actual app uses a different `src` layout.

```txt
src/
  app/
    page.tsx
    layout.tsx
    api/
      roles/
        route.ts
      generate-answer-bank/
        route.ts
      generate-pitch/
        route.ts
      generate-follow-up/
        route.ts

  components/
    app-shell/
      JobHunterShell.tsx
      AppHeader.tsx
      OpportunityRail.tsx
      OpportunitySelector.tsx
      MobileOpportunityPicker.tsx

    prep-workspace/
      PrepWorkspace.tsx
      TodaysBriefCard.tsx
      NextStepCard.tsx
      PrepBriefSection.tsx
      AnswerBankSection.tsx
      AnswerItem.tsx
      FollowUpDraftSection.tsx
      MoreToolsSection.tsx
      ToolCard.tsx
      EmptyState.tsx
      SectionCard.tsx
      CollapsibleSection.tsx

    ui/
      Button.tsx
      Badge.tsx
      Card.tsx
      IconButton.tsx
      Textarea.tsx
      Input.tsx
      Skeleton.tsx

  lib/
    prep/
      nextStepRules.ts
      prepDerivations.ts
      fallbackContent.ts
      sectionConfig.ts
      types.ts

    trigger/
      client.ts
      tasks.ts
      status.ts

  trigger/
    generateAnswerBank.ts
    generatePitch.ts
    generateFollowUp.ts
    refreshCompanyIntel.ts

  styles/
    globals.css
```

---

## Top-Level Component Tree

```txt
<App />
  <JobHunterShell>
    <AppHeader />

    <OpportunityRail />                desktop only
    <MobileOpportunityPicker />        mobile only

    <PrepWorkspace>
      <TodaysBriefCard />
      <NextStepCard />
      <PrepBriefSection />
      <AnswerBankSection>
        <AnswerItem />
      </AnswerBankSection>
      <FollowUpDraftSection />
      <MoreToolsSection>
        <ToolCard />
      </MoreToolsSection>
    </PrepWorkspace>
  </JobHunterShell>
```

---

## Page-Level Layout

### `app/page.tsx`
Responsibility:
- Load or receive role/prep data
- Determine active opportunity
- Pass normalized props to `JobHunterShell`
- Avoid UI detail logic here

Suggested shape:

```tsx
export default async function Page() {
  const roles = await getRoles();
  const activeRole = getActiveRole(roles);
  const prepState = await getPrepState(activeRole?.id);

  return (
    <JobHunterShell
      roles={roles}
      activeRole={activeRole}
      prepState={prepState}
    />
  );
}
```

If data is currently client-only/local, keep this as a client component wrapper until persistence is clarified.

---

## App Shell Components

### `JobHunterShell.tsx`
Responsibility:
- Own shell layout
- Desktop two-column layout
- Mobile stacked layout
- Pass active role/prep props down

Structure:

```tsx
export function JobHunterShell({ roles, activeRole, prepState }: Props) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader />
      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-6 md:grid-cols-[280px_minmax(0,1fr)]">
        <OpportunityRail roles={roles} activeRoleId={activeRole?.id} />
        <MobileOpportunityPicker roles={roles} activeRoleId={activeRole?.id} />
        <PrepWorkspace activeRole={activeRole} prepState={prepState} />
      </main>
    </div>
  );
}
```

### `AppHeader.tsx`
Show only:
- `Job Hunter`
- `Prep workspace`
- `New role` button
- optional small save/last updated microcopy

Avoid:
- Hero copy
- Metrics
- Large banners

### `OpportunityRail.tsx`
Desktop only.

Each role row shows:
- Company
- Role title
- Stage badge
- Interview/date microcopy

Do not show:
- Scores
- Compensation
- Resume match
- Long notes

### `MobileOpportunityPicker.tsx`
Mobile only.

Use either:
- Compact dropdown
- Horizontal chips

Do not duplicate the full rail content.

---

## Prep Workspace Components

### `PrepWorkspace.tsx`
Responsibility:
- Render the exact section order
- Keep page calm and readable
- Use derived prep state helpers, not inline clutter

Required order:

```tsx
export function PrepWorkspace({ activeRole, prepState }: Props) {
  const nextStep = getNextStep({ activeRole, prepState });
  const brief = buildTodaysBrief({ activeRole, prepState });

  return (
    <section className="mx-auto w-full max-w-3xl space-y-4">
      <TodaysBriefCard brief={brief} />
      <NextStepCard nextStep={nextStep} />
      <PrepBriefSection activeRole={activeRole} prepState={prepState} />
      <AnswerBankSection answers={prepState.answers} />
      <FollowUpDraftSection draft={prepState.followUpDraft} />
      <MoreToolsSection activeRole={activeRole} prepState={prepState} />
    </section>
  );
}
```

### `TodaysBriefCard.tsx`
Visible fields only:
- Role title + company
- Stage
- Interview date/time or `Add interview date`
- Top 3 prep tasks
- 60-second pitch preview, max 2 lines

Fallback tasks:
1. Review the job description
2. Tighten your 60-second pitch
3. Prepare 3 STAR stories

### `NextStepCard.tsx`
Exactly one primary CTA.

Rule order:
1. Intake incomplete → `Complete role details`
2. No answer bank → `Generate answer bank`
3. No pitch → `Create 60-second pitch`
4. Otherwise → `Practice key answers`

Secondary action:
- `Edit role details`

### `PrepBriefSection.tsx`
Default open.

Show:
- Short role summary
- What they likely care about
- Your positioning angle
- 3 focus bullets

Do not show:
- Long company intel dumps
- Scores
- Multicolumn analytics

### `AnswerBankSection.tsx`
Default open if answers exist.

Rules:
- Show max 5 answers by default
- First answer expanded
- Remaining answers collapsed
- Each answer preview max 2 lines

Actions:
- `Regenerate answers`
- `Add custom answer`

### `AnswerItem.tsx`
Responsibility:
- One question + answer
- Collapsible content
- Optional notes

Visible collapsed state:
- Question
- 2-line answer preview

Expanded state:
- Full answer
- Notes/talking points if present

### `FollowUpDraftSection.tsx`
Default open only if draft exists.

Show:
- Subject
- Body preview
- Copy button
- Edit button

If empty:
- Small collapsed empty state
- CTA: `Draft follow-up`

### `MoreToolsSection.tsx`
Collapsed by default.

Move noisy features here:
- Resume Intelligence
- Role Grade
- Company Intel
- Compensation Model
- Recruiter Network
- Mock Interview
- Metrics / analytics

Render as simple tool cards, not expanded dashboards.

### `ToolCard.tsx`
Each card contains:
- Tool name
- One sentence description
- One action button/link

---

## Utility Files

### `lib/prep/types.ts`
Centralize domain types.

```ts
export type RoleStage =
  | 'saved'
  | 'applied'
  | 'screening'
  | 'interviewing'
  | 'offer'
  | 'rejected';

export type Role = {
  id: string;
  company: string;
  title: string;
  stage: RoleStage;
  interviewAt?: string | null;
  jobDescription?: string | null;
  notes?: string | null;
};

export type PrepAnswer = {
  id: string;
  question: string;
  answer: string;
  notes?: string | null;
};

export type FollowUpDraft = {
  subject: string;
  body: string;
};

export type PrepState = {
  pitch?: string | null;
  prepBrief?: string | null;
  answers: PrepAnswer[];
  followUpDraft?: FollowUpDraft | null;
  companyIntel?: unknown;
  resumeIntel?: unknown;
};
```

### `lib/prep/nextStepRules.ts`
Keep CTA rules pure and testable.

```ts
export type NextStep = {
  label: string;
  description: string;
  actionId:
    | 'complete-role-details'
    | 'generate-answer-bank'
    | 'create-pitch'
    | 'practice-key-answers';
};

export function getNextStep({ activeRole, prepState }: Params): NextStep {
  if (!activeRole?.company || !activeRole?.title || !activeRole?.jobDescription) {
    return {
      label: 'Complete role details',
      description: 'Add the basics so your prep has enough context.',
      actionId: 'complete-role-details',
    };
  }

  if (!prepState.answers?.length) {
    return {
      label: 'Generate answer bank',
      description: 'Create five tailored answers for this opportunity.',
      actionId: 'generate-answer-bank',
    };
  }

  if (!prepState.pitch) {
    return {
      label: 'Create 60-second pitch',
      description: 'Turn your experience into a tight opening answer.',
      actionId: 'create-pitch',
    };
  }

  return {
    label: 'Practice key answers',
    description: 'Review your strongest answers before the interview.',
    actionId: 'practice-key-answers',
  };
}
```

### `lib/prep/fallbackContent.ts`
Keep fallback copy centralized.

```ts
export const FALLBACK_TOP_TASKS = [
  'Review the job description',
  'Tighten your 60-second pitch',
  'Prepare 3 STAR stories',
];
```

### `lib/prep/prepDerivations.ts`
Use this for derived display state.

Responsibilities:
- Build Today’s Brief data
- Format interview date
- Create answer preview strings
- Determine empty states

### `lib/prep/sectionConfig.ts`
Centralize More Tools config.

```ts
export const MORE_TOOLS = [
  {
    id: 'resume-intelligence',
    title: 'Resume Intelligence',
    description: 'Compare your resume positioning against this role.',
  },
  {
    id: 'company-intel',
    title: 'Company Intel',
    description: 'Review company context when you need deeper prep.',
  },
  {
    id: 'mock-interview',
    title: 'Mock Interview',
    description: 'Practice under pressure when your answer bank is ready.',
  },
];
```

---

## Trigger.dev File Structure

Do not block P0 UI cleanup on Trigger.dev. Add it only where async generation is already painful or timeout-prone.

### Recommended Trigger tasks

```txt
src/trigger/
  generateAnswerBank.ts
  generatePitch.ts
  generateFollowUp.ts
  refreshCompanyIntel.ts
```

### `trigger/generateAnswerBank.ts`
Purpose:
- Accept role/resume/prep context
- Generate max 5 tailored answers
- Save results to existing persistence layer
- Return task status/result

### `trigger/generatePitch.ts`
Purpose:
- Generate short 60-second pitch
- Keep output concise
- Save pitch to prep state

### `trigger/generateFollowUp.ts`
Purpose:
- Generate a follow-up email draft
- Save subject/body

### `trigger/refreshCompanyIntel.ts`
Purpose:
- Future/P1 only
- Run in background
- Keep output inside More Tools, not default view

---

## API Routes for Trigger

```txt
src/app/api/generate-answer-bank/route.ts
src/app/api/generate-pitch/route.ts
src/app/api/generate-follow-up/route.ts
```

Each route should:
1. Validate active role ID/context
2. Trigger the background task
3. Return task/run ID immediately
4. Let UI show pending state

Do not make the frontend wait synchronously for AI output.

---

## UI State Rules

### Keep local UI state local
Use simple React state for:
- Active collapsed answer item
- More Tools expanded/collapsed
- Mobile opportunity picker open/closed

### Persist only meaningful user content
Persist:
- Roles
- Prep brief
- Answers
- Pitch
- Follow-up draft
- Notes

Do not persist in P0 unless already easy:
- Collapse state
- Active section scroll position
- Temporary UI toggles

---

## Styling Rules

### Layout width
Main workspace:
- `max-w-3xl` or roughly 720–900px

### Cards
- One card per section
- Ample padding
- Minimal borders
- Light shadow only if current design already uses it

### Typography
Use four levels only:
1. App/page title
2. Section title
3. Body text
4. Microcopy

### Buttons
- One primary CTA above the fold
- Secondary actions are text buttons or low-emphasis buttons

### Avoid
- Metric grids
- Multi-column dashboards
- Big hero panels
- Full-width dense tables
- More than one accent color fighting for attention

---

## Suggested Implementation Sequence

1. Create backup branch from actual production/source branch.
2. Identify existing page/component that renders current prep dashboard.
3. Create `PrepWorkspace` and section components.
4. Move existing content into new minimal sections without deleting data.
5. Move secondary-heavy content into `MoreToolsSection`.
6. Add pure `getNextStep` rule utility.
7. Wire primary CTA actions.
8. QA desktop/mobile.
9. Optional: add Trigger.dev for `generate-answer-bank` only.
10. Report preview URL and rollback point.

---

## P0 Definition of Done

- User sees active opportunity context first.
- Today’s Brief appears before long content.
- Exactly one primary Next Step CTA appears above the fold.
- Prep Brief, Answer Bank, and Follow-Up Draft are the only major default sections.
- More Tools is collapsed by default.
- Existing generated content remains accessible.
- No backend schema change unless unavoidable.
- Backup branch/commit/deployment is documented.
- Mobile view is calm and usable.
