---
name: opencode-delegate
description: Hand bounded, low-judgment grunt work to a free opencode model via `oc-delegate` to save Claude usage — boilerplate, test scaffolding, docstrings or type hints where the code and tests make the types clear, README drafts, format conversions, fixture/data files, and annotation or call-site sweeps across several files. Use proactively when a job is big in output but small in judgment, roughly 150+ lines of new content or hand edits across several files; smaller jobs, and anything one sed/perl command can do, are cheaper done directly. Consult it before reading the files you might hand off: it explains how to size the job with `git ls-files` and `wc -l` and delegate it in about four tool calls. Also use whenever the user says "/opencode-delegate", "use opencode", "delegate this" or "use the free model". Not for design decisions, subtle debugging, security-sensitive code, or anything near secrets.
allowed-tools: Bash(oc-delegate:*), Bash(git status:*), Bash(git diff:*), Bash(git ls-files:*), Bash(wc:*)
---

# opencode-delegate

`oc-delegate [-m provider/model]... [-c "check command"] [-r retries] "task"` (`~/.local/bin/oc-delegate`) runs the opencode agent `cc-worker` (`~/.config/opencode/agents/cc-worker.md`) in the current directory with free models. It prints the model that succeeded, the files it changed, the check result, any failed tool calls, then the worker's own summary.

Fallback is automatic. If a model returns a run error (rate limit, quota, unavailable, provider error), has no output or network traffic for 180s (`OC_DELEGATE_IDLE`) or passes 300s (`OC_DELEGATE_TIMEOUT`), the wrapper reverts only the files that model edited and tries the next model. Files changed by anyone else during the run are left alone and listed on stderr. The whole run stops by 540s (`OC_DELEGATE_TOTAL`), so it always returns inside a 600000 ms Bash timeout. Exit 1 with "all models failed" means every model failed or time ran out, and the tree is back to its pre-run state.

With `-c`, the wrapper runs the check command in the repo root after the worker finishes. If it fails, the wrapper sends the last 60 lines of its output back to the same worker session, up to `-r` times (default 2). If it still fails, that model counts as failed and the next one is tried. The output then has a `check:` line: `passed`, `passed after N retries`, or `already failing before the run; skipped` when the check failed on the untouched tree. The check runs in the same kind of sandbox as the worker, without network.

On success the wrapper also adds a missing final newline to text files the worker edited, before running the check, and lists them on a `newline:` line. Don't spend your own turns on that.

Every model attempt appends a TSV line to `~/.local/state/oc-delegate.log` (override with `OC_DELEGATE_LOG`): time, ok/fail, model, duration, repo, files changed or error, task, check result.

The worker's sandbox:
- It can list files, find files by name, read, and edit/create files inside the current directory.
- It has no shell, no grep, no web, no subagents, and no access outside the directory. Only the wrapper runs the `-c` check.
- It cannot read or edit `.git`, `.env*`, `*secret*`, `*credentials*`, `*.pem`, `*.key` or ssh keys.
- With `bwrap` installed (Linux), it also runs in a filesystem sandbox: only the repo (minus `.git`) and opencode's own data dirs are writable.
- It refuses to run outside a git repo, so edits to tracked and untracked files are reviewable with `git diff`. Edits to gitignored files are not; the wrapper lists those under `not in git diff`.

## When to delegate

Delegating has a fixed cost, paid in your own turns: every tool call re-reads the whole conversation. In a benchmark on Opus 5.5, delegating small jobs (docstrings for one module, one small test file) cost 4–17% more than writing them directly. Docstrings for 19 functions across six modules only broke even (−15% and +8% in two rounds), because Claude read every file before delegating and then polished the worker's output. So delegate when you would otherwise write roughly 150+ lines of new content, or make hand edits across several files, and keep your own turns around it to the few in "How". Below that size, do it yourself.

Good fits, at that size:
- Boilerplate following an existing example file (new endpoints/components/tests shaped like a sibling).
- Test scaffolding, with the project's test command as the `-c` check.
- Hand edits across several known files that no single command can make: adapting call sites to a new signature, adding type hints where the tests and call sites make the types clear, converting a pattern that varies per site.
- Docstrings, README sections, changelog drafts, data/fixture files, format conversions.

Do it yourself instead when:
- It's below that size, or writing the prompt would cost about as much as doing the task.
- One command does it: a rename or substitution with `sed`/`perl`, a formatter, a codemod.
- It needs judgment: architecture, tricky bugs, performance, concurrency, auth/crypto/security, or types the code doesn't make clear.
- Getting it right takes more than one check command: debugging, exploring output, trying things.
- The repo is private/confidential work, or secrets live in files the deny list doesn't catch — unless the user has OK'd delegation there.
- The repo or user forbids AI-written contributions.

## How

Every tool call re-reads the whole context, so each extra turn costs more than the output tokens it saves. Aim for about four calls: size up, delegate, read the diff, fix.

1. Decide from `git ls-files` and `wc -l`, not by reading the files. The worker reads them. If you have already read them, fine; don't read more.
2. Write a short, self-contained prompt. The worker has none of this conversation's context. Name an example file to copy style from instead of quoting it:

   ```
   Goal: <one sentence>. Done when: <check>.
   Files to change: <paths>. Copy style from: <path>.
   Constraints: no other files, no new dependencies, no comments.
   ```

   Never put secrets in the prompt. Split jobs that need thousands of lines of new output into several calls: some free endpoints send nothing until a large write is complete, and that looks like a hang.
3. Run everything in one Bash call with a timeout of 600000, using the project's test command as the check:

   ```
   git status --porcelain && oc-delegate -c "<test command>" "<prompt>" && git diff --stat
   ```

   The first part shows the existing changes, so you can tell the worker's edits apart from the user's. Leave out `-c` only if the project has no fast, offline test command.
4. Read `git diff` once.
   - Fix only what is wrong: bugs, wrong behaviour, missed requirements. Don't rewrite wording, line length or style you'd have chosen differently.
   - If the output says `check: passed`, don't rerun those tests or write your own verification scripts. Run the tests yourself only after your own fixes, or when there was no check or it was skipped.
   - Read every file listed under `not in git diff`. Git can't revert those, so restore or delete them yourself if they're wrong, and tell the user.
   - If the result is mostly wrong, revert only the files the worker touched or created (never the user's earlier changes) and do the task yourself.
5. Tell the user in one line that the free model did the work and what you verified.

## Models

- Default chain, tried in order: `beam-free` → `deepseek-v4.1-flash-free` → `space-bunny-free` → `mimo-v2.6-flash-free` → `big-pickle`, all under `opencode/`. Override the chain with repeated `-m` flags or `OC_DELEGATE_MODELS="a b c"`.
- Run errors, hangs, runs that use up their steps, malformed tool calls and failing checks are handled by the wrapper. A run that passes the check but is still wrong is not: revert the worker's files yourself, then either retry with `-m` starting at the next model or do the task yourself. Don't retry more than once.
- If "all models failed", do the task yourself and tell the user the free models were unavailable.
- Benchmarked 2026-10-18 (docstrings, tests, multi-file rename; 2 runs each): deepseek-v4.1-flash-free, big-pickle and mimo-v2.6-flash-free passed every task. beam-free is fastest but once made malformed tool calls. space-bunny-free wrote failing tests in both test runs (it passed 3 of 3 with `-c` on 2026-10-19), and it's an anonymous preview that may disappear.
- Avoid `glm-5.3-flash-free` (endpoint often unavailable, 80–90s to fail) and `nemotron-3.5-lightning-free` (hangs). `longcat-2.5-preview-free` and `nemotron-3.5-super-vl-free` work but are slow and wrote wrong test assertions.
- The free lineup changes; list the current models with `opencode models | grep free`.

## Privacy

Free OpenCode Zen models may log prompts and use them for training. Everything the worker reads in the repo goes to that provider. If you are unsure whether a repo is fine to share, ask the user before the first delegation in it.
