# AGENTS.md

## Scope

This file applies to coding agents working in this repository.
Human collaborators are not expected to follow this workflow.

## Worktree Rules

- Any non-temporary development task MUST start by reviewing all existing git worktrees.
- Before starting new work, the agent MUST run `git worktree list` and identify any unfinished branches.
- If unfinished worktrees exist, the agent MUST either:
  - finish, merge, or discard them first, or
  - explicitly record the blocker and get user approval before opening another long-lived worktree.
- Any non-temporary development MUST happen in a `codex/*` worktree, not directly in the main workspace.
- Temporary one-off inspection or debugging commands may run outside a worktree if they do not create long-lived code changes.

## Superpowers Rules

The following rules define when and how to use Superpowers skills.
See Required Skill Mapping for the specific skill to invoke.

- New feature request:
  - first create or confirm a spec
  - then create an implementation plan
  - only then begin implementation
- Bug report or suspicious result:
  - first run a minimal diagnosis
  - print or inspect the key runtime state needed to identify the root cause
  - do not patch code before the cause is understood
- Any code change:
  - write or update tests first
  - confirm the test fails for the intended reason
  - then implement the fix or feature

## Required Skill Mapping

- New feature or behavior change:
  - use `brainstorming`
  - then `writing-plans`
- Multi-step implementation from an approved plan:
  - use `subagent-driven-development` if available
  - otherwise `executing-plans`
- Bug, failed test, or abnormal result:
  - use `systematic-debugging`
- Before writing implementation code:
  - use `test-driven-development`
- Before claiming completion:
  - use `verification-before-completion`
- When finishing a branch:
  - use `finishing-a-development-branch`

## Completion Rules

- After implementation, the agent MUST run fresh verification before claiming success.
- If verification fails, the agent MUST NOT merge or clean up.
  Report the failure and wait for user instruction.
- Default completion behavior is:
  - merge back to `main`
  - remove the finished worktree
  - delete the finished branch
- A worktree may be kept only if the user explicitly asks to keep it, or if there is a documented blocker.
- If a blocker prevents cleanup, the agent MUST report:
  - the blocked worktree
  - the blocker
  - the next required action

## Branch Hygiene

- Long-lived unfinished worktrees MUST be resolved before new work begins.
- Agents MUST NOT create additional parallel branches while unfinished branches exist, unless the user explicitly approves.
- If a branch has been superseded by work already merged to `main`, the agent should recommend deleting it.

## Exceptions

- These rules may be overridden only by explicit user instruction.
