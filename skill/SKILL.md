---
name: opencode-delegate
description: Hand bounded, low-judgment grunt work to a free opencode model via `oc-delegate` to save Claude usage — boilerplate, test scaffolding, repetitive mechanical edits across a few files, docstrings/README drafts, format conversions, filling in data files. Use proactively when a task is big in output but small in judgment, and whenever the user says "/opencode-delegate", "use opencode", "delegate this" or "use the free model". Not for design decisions, subtle debugging, security-sensitive code, or anything near secrets.
allowed-tools: Bash(oc-delegate:*), Bash(git status:*), Bash(git diff:*)
---

# opencode-delegate

`oc-delegate [-m provider/model]... "task"` (`~/.local/bin/oc-delegate`) runs the opencode agent `cc-worker` (`~/.config/opencode/agents/cc-worker.md`) in the current directory with free models. It prints the model that succeeded, the files it changed, any failed tool calls, then the worker's own summary.

Fallback is automatic. If a model returns a run error (rate limit, quota, unavailable, provider error), goes silent for 120s (`OC_DELEGATE_IDLE`) or passes 600s total (`OC_DELEGATE_TIMEOUT`), the wrapper reverts only the files that model edited and tries the next model. Files changed by anyone else during the run are left alone and listed on stderr. Exit 1 with "all models failed" means every model failed and the tree is back to its pre-run state.

Every model attempt appends a TSV line to `~/.local/state/oc-delegate.log` (override with `OC_DELEGATE_LOG`): time, ok/fail, model, duration, repo, files changed or error, task.

The worker's sandbox:
- It can list files, find files by name, read, and edit/create files inside the current directory.
- It has no shell, no grep, no web, no subagents, and no access outside the directory.
- It cannot read or edit `.env*`, `*secret*`, `*credentials*`, `*.pem`, `*.key` or ssh keys.
- It refuses to run outside a git repo, so every edit stays reviewable with `git diff`.

## When to delegate

Good fits:
- Boilerplate following an existing example file (new endpoint/component/test shaped like a sibling).
- Test scaffolding for code you have already read and understood.
- Mechanical edits across a handful of known files (rename a field, update call sites you list).
- Docstrings, README sections, changelog drafts, data/fixture files, format conversions.

Do it yourself instead when:
- Writing the prompt would cost about as much as doing the task.
- It needs judgment: architecture, tricky bugs, performance, concurrency, auth/crypto/security.
- It needs running commands to get right (the worker cannot run tests or builds).
- The repo is private/confidential work, or secrets live in files the deny list doesn't catch — unless the user has OK'd delegation there.
- The repo or user forbids AI-written contributions.

## How

1. Run `git status --porcelain` and note existing changes, so you can tell the worker's edits apart from the user's.
2. Write a self-contained prompt. The worker has none of this conversation's context. Include:
   - the goal and done criteria;
   - exact file paths to read and to change;
   - an example file to copy style from;
   - constraints: no other files, no new dependencies, no comments beyond the existing density.
   Never put secrets in the prompt.
3. Run `oc-delegate "<prompt>"` with a Bash timeout of 600000.
4. Review the result:
   - Check `git diff --stat`, then read the full diff of every file it touched.
   - Run the project's tests, linters or build yourself.
   - Fix small problems directly.
   - If the result is mostly wrong, revert only the files the worker touched or created (never the user's earlier changes) and do the task yourself.
5. Tell the user in one line that the free model did the work and what you verified.

## Models

- Default chain, tried in order: `deepseek-v4.1-flash-free` → `glm-5.3-flash-free` → `mimo-v2.6-flash-free` → `big-pickle`, all under `opencode/`. Override the chain with repeated `-m` flags or `OC_DELEGATE_MODELS="a b c"`.
- Run errors and hangs are handled by the wrapper. A run that succeeds but gives a wrong result is not: revert the worker's files yourself, then either retry with `-m` starting at the next model or do the task yourself. Don't retry more than once.
- If "all models failed", do the task yourself and tell the user the free models were unavailable.
- Avoid `nemotron-3-ultra-free`: it hung with no output when tested on 2026-10-16.
- The free lineup changes; list the current models with `opencode models | grep free`.

## Privacy

Free OpenCode Zen models may log prompts and use them for training. Everything the worker reads in the repo goes to that provider. If you are unsure whether a repo is fine to share, ask the user before the first delegation in it.
