---
name: spec-review
description: Reviews the diff since a fixed point (commit, branch, tag) against the spec and ticket that originated it — requirements missing, implemented wrong, or scope creep. Use after Codex finishes a ticket and before the owner checks it in 3ds Max, or when the user asks to check work against a spec or ticket.
---

Single-axis review of the diff between `HEAD` and a fixed point: does the code faithfully implement the originating spec and ticket? Code quality and style are out of scope.

The tracker layout is in `.docs/agents/issue-tracker.md`.

## Process

### 1. Pin the fixed point

Take it from the user, or from the `**База:**` line of the ticket's plan in `.scratch/<feature>/plans/`. If neither exists, ask.

Confirm it resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff fails here, not halfway through.

The diff is `git diff <fixed-point>...HEAD` plus uncommitted work (`git diff HEAD`, `git status --short` for new files) — Codex often leaves the ticket uncommitted.

### 2. Find the spec

In this order:

1. A path the user passed.
2. The ticket under `.scratch/<feature>/issues/` and the spec `.scratch/<feature>/spec.md` next to it.
3. Nothing found — ask. If there is no spec, stop and report "no spec available".

Read the ticket's plan too: the verdict and any `## Отклонения` section are part of what was agreed.

### 3. Review

Run inline, no sub-agents. Read the spec and ticket in full, then the diff in full. Report:

- **(a) Missing or partial** — asked for, not in the diff.
- **(b) Scope creep** — in the diff, not asked for. Check the spec's **Out of Scope** section explicitly: it is the cheapest signal.
- **(c) Implemented but wrong** — looks addressed, but does not match what the spec describes.

Quote the spec or ticket line for each finding and cite the file and hunk. Keep the report under 400 words.

### 4. Summarise

One line: total findings, and the worst one.

## 3ds Max notes

A requirement can be met in the logic and still be unreachable for the user. Check the wiring, not only the core:

- A new tool is reachable: the macroscript (`.mcr`) is defined and its category and name match what the spec promises in the UI.
- Every rollout control the spec mentions has a handler, and the handler calls the core function, not a stub.
- A new `.ms` file is actually loaded: `fileIn` / `include` path exists and is in load order before its first use.
- Install or startup scripts copy and register new files; a file that exists only in `src/` is not installed.
- Operations the spec calls undoable are wrapped in `undo on` / `undo "<name>" on`.
- If tests exist in `tests/`, behaviour the spec names has a test, and changed behaviour changed its test.
