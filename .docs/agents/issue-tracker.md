# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/` (gitignored).

## Layout

```
.scratch/
  inbox/                  ← quick notes mid-work, Status: needs-planning
  <feature-slug>/
    spec.md
    issues/NN-<slug>.md   ← one file per ticket, numbered from 01
    plans/NN-<slug>.md    ← Codex plan per ticket, verdict appended by Claude
```

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Each issue file has `**Status:**` and `**Дата:**` lines near the top; `Дата` is when the status became current
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## Status vocabulary

| Value | Meaning |
|---|---|
| `needs-planning` | needs `/grill-me` before any code |
| `ready-for-agent` | self-contained, can be planned and built |
| `in-progress` | being worked on now |
| `done` | verified in 3ds Max by the owner |

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.
