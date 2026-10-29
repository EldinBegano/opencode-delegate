# opencode-delegate

A [Claude Code](https://claude.com/claude-code) skill that hands low-judgment grunt work to free [opencode](https://opencode.ai) models, so your Claude usage goes to the parts that need it.

Claude stays in charge. It decides what to delegate, writes the prompt, runs the free model through a sandboxed worker, then reviews the diff and runs the tests itself.

![Claude Code loading the skill, delegating 33 docstrings to a free model with the tests as the check, then reviewing the diff](docs/demo.gif)

A real headless Claude Code session (`claude -p`) on the benchmark fixture, redrawn as a terminal with the waits cut out. Claude loads the skill, hands 33 docstrings across eight modules to `beam-free` with the tests as the check, reviews the diff and fixes one word. The session cost $0.31 of Claude usage. In round 3 the same task averaged $0.63 without the skill.

## How it works

```
Claude Code
  └─ opencode-delegate skill        decides a task is grunt work, writes a self-contained prompt
       └─ oc-delegate "task"        wrapper script on your PATH
            └─ opencode run --standalone --agent cc-worker -m <free model>
                 ├─ success → prints model, changed files, worker summary
                 └─ error / 180s idle / 300s → reverts that model's edits, tries next model
                                                (whole run capped at 540s)
```

- **`skill/SKILL.md`**: tells Claude when to delegate (boilerplate, test scaffolding, docs drafts, fixtures, format conversions, mechanical edits across a few files), when not to (design, tricky bugs, security, anything that needs a shell), and how to review the result.
- **`bin/oc-delegate`**: runs the worker with a fallback chain of free models. If a model fails, hangs or times out, the wrapper reverts only the files that model edited and tries the next one. Your own uncommitted changes are left alone. If `bwrap` is installed, the worker runs in a sandbox where only the repo (minus `.git`) and opencode's own data dirs are writable. Every attempt is logged.
- **`opencode/cc-worker.md`**: a locked-down opencode agent. It can list, read and edit files in the current directory, and nothing else: no shell, no grep, no web, no subagents, no paths outside the directory, and no reading or editing `.git`, `.env*`, `*secret*`, `*credentials*`, `*.pem`, `*.key` or SSH keys.
- **`claude-md-snippet.md`**: a `CLAUDE.md` section that makes delegation Claude's default for grunt work. Without it, Claude rarely picks the skill on its own.

The wrapper refuses to run outside a git repo, so edits to tracked and untracked files show up in `git diff`. Edits to gitignored files don't, so the wrapper lists them separately under `not in git diff`.

## Requirements

| Need | Notes |
| --- | --- |
| Claude Code | Any recent version with skills support. |
| [opencode](https://opencode.ai) | Tested with v2.0.32 and v2.1.3. Needs `opencode run --standalone --format json`. The free OpenCode Zen models work without an API key. |
| `bash`, `git`, `jq` | `jq` parses opencode's JSON event stream. |
| GNU coreutils | `stat -c`, `realpath -m`, `date -Is`. Linux has these. On macOS, install `coreutils` with Homebrew and put its `gnubin` directory first on `PATH`. |
| `~/.local/bin` on `PATH` | Where the installer puts `oc-delegate`. |
| `bwrap` (optional, Linux) | [bubblewrap](https://github.com/containers/bubblewrap) sandboxes the worker's filesystem writes. Without it, the worker relies on opencode's permission rules alone. |
| `ss`, `pgrep` (optional, Linux) | From iproute2 and procps. The wrapper uses them to tell a slow model from a hung one by its network traffic. Without them, only opencode's output counts. |

Install opencode if you don't have it:

```sh
curl -fsSL https://opencode.ai/install | bash
opencode models | grep -E -- '-free|big-pickle'
```

The second command should list some free models. If none of the default chain's models appear, see [Models](#models).

## Let Claude Code set it up

Paste this into Claude Code:

```text
Install the opencode-delegate skill from https://github.com/EldinBegano/opencode-delegate for me.

1. Check the requirements in its README: bash, git, jq, GNU coreutils and opencode. If anything is missing, tell me how to install it on my system and stop. Don't install system packages yourself.
2. Clone the repo to ~/.local/share/opencode-delegate, or git pull if it's already there. Read install.sh, then run it. If it warns that ~/.local/bin is not on PATH, tell me the line to add to my shell config.
3. Add "Bash(oc-delegate:*)" to permissions.allow in ~/.claude/settings.json and keep everything else in that file. If you can't edit it, show me the exact JSON to add.
4. Append claude-md-snippet.md to ~/.claude/CLAUDE.md, unless that file already has an "# opencode delegation" section.
5. Run the smoke test from the README in a temporary git repo and show me the oc-delegate output and the git diff.
6. Summarize what you changed. Don't approve any repos for delegation; I'll answer when you first ask.
```

Start a new Claude Code session afterwards so the skill and the CLAUDE.md section load.

## Manual setup

### 1. Clone and install

```sh
git clone https://github.com/EldinBegano/opencode-delegate.git
cd opencode-delegate
./install.sh
```

The installer checks the requirements, then symlinks three files into place:

| File | Installed to |
| --- | --- |
| `skill/SKILL.md` | `~/.claude/skills/opencode-delegate/SKILL.md` |
| `opencode/cc-worker.md` | `~/.config/opencode/agents/cc-worker.md` |
| `bin/oc-delegate` | `~/.local/bin/oc-delegate` |

Because they are symlinks, `git pull` updates your install. Use `./install.sh --copy` if you'd rather copy the files and delete the clone. An existing file that differs from the repo version is moved to `<file>.bak.<timestamp>` first. Rerunning the installer is safe. `CLAUDE_CONFIG_DIR` and `XDG_CONFIG_HOME` are respected.

### 2. Allow the wrapper

Add this to `~/.claude/settings.json` so Claude can run `oc-delegate` without a permission prompt each time:

```json
{
  "permissions": {
    "allow": ["Bash(oc-delegate:*)"]
  }
}
```

Merge it into the existing `permissions.allow` list if you already have one.

### 3. Make delegation the default

Paste [`claude-md-snippet.md`](claude-md-snippet.md) into `~/.claude/CLAUDE.md`. This step matters. With only the skill installed, Claude tends to just write grunt work itself.

The snippet keeps a list of repos you've approved for the free models. Before the first delegation in a new repo, Claude asks you once and adds the repo to the list if you say yes.

### 4. Smoke test

```sh
tmp=$(mktemp -d) && cd "$tmp" && git init -q
printf 'a\nb\n' > list.txt && git add . && git commit -qm init
oc-delegate "Append a line containing exactly 'c' to list.txt. Change no other file."
git diff
tail -n 1 ~/.local/state/oc-delegate.log
```

Expected output, roughly:

```
model: opencode/beam-free
changed:
  M	list.txt
---
Changed list.txt only: appended a third line containing exactly 'c'.
```

Then start Claude Code in a real repo and ask for something like "add docstrings to every public function in `src/utils.py`". Claude should hand it to `oc-delegate`, then review the diff.

## Usage

Most of the time you don't call anything. Claude delegates when a task fits, and tells you in one line what the free model did and what it checked afterwards.

To force it, say "delegate this", "use opencode" or "use the free model", or type `/opencode-delegate`.

You can also run the wrapper yourself from inside any git repo:

```sh
oc-delegate "task"                                       # default model chain
oc-delegate -m opencode/deepseek-v4.1-flash-free "task"   # one model, no fallback
oc-delegate -m model-a -m model-b "task"                 # your own chain
oc-delegate -c "pytest -q" "task"                        # run a check after the worker, send failures back
```

### Check loop

With `-c "command"` (or `OC_DELEGATE_CHECK`), the wrapper runs the command in the repo root after the worker finishes. If it fails, the wrapper continues the same opencode session with the last 60 lines of the check's output and asks the worker to fix the cause, up to `-r` times per model (default 2). If the check still fails, that model counts as failed: its files are reverted and the next model is tried. The worker itself still has no shell; only the wrapper runs the command.

The check first runs once on the untouched tree. If it already fails there, the wrapper prints `check: already failing before the run; skipped` and runs the worker without the loop, so it doesn't chase failures it didn't cause.

The output gets a `check:` line after the changed files: `passed`, `passed after N retries`, or the skip. With `bwrap`, the check runs sandboxed without network: the filesystem is read-only except the repo (minus `.git`) and a private `/tmp`. It runs code the worker wrote, so it needs the sandbox more than the worker does. Retries and checks count against the same per-model and overall time limits.

After a successful worker run, the wrapper adds a missing final newline to each text file the worker edited and lists them on a `newline:` line. It does this before running the check, so checks see the same bytes Claude will review. Binary files, symlinks and files outside the repo are left alone. The worker's edit tool usually leaves the last line unterminated, and fixing that used to be Claude's most common extra turn.

### Settings

| Variable | Default | Effect |
| --- | --- | --- |
| `OC_DELEGATE_MODELS` | the chain below | Space-separated model chain, used when no `-m` is given. |
| `OC_DELEGATE_TIMEOUT` | `300` | Seconds before a model run is killed and the next model is tried. |
| `OC_DELEGATE_IDLE` | `180` | Seconds with no opencode output and no network traffic before a model counts as hung. |
| `OC_DELEGATE_TOTAL` | `540` | Seconds for the whole run across all models. Keep it below Claude Code's 600s Bash timeout. |
| `OC_DELEGATE_CHECK` | none | Check command, used when no `-c` is given. |
| `OC_DELEGATE_RETRIES` | `2` | Follow-up attempts per model when the check fails, used when no `-r` is given. |
| `OC_DELEGATE_CHECK_TIMEOUT` | `120` | Seconds per check run. |
| `OC_DELEGATE_SANDBOX` | `1` | Set to `0` to run the worker and the check without `bwrap`. |
| `OC_DELEGATE_TAIL` | `40` | Lines of the worker's summary to print. |
| `OC_DELEGATE_LOG` | `~/.local/state/oc-delegate.log` | Where attempts are logged. |

opencode prints nothing while a model writes a file in a single tool call, so the idle timer also watches the worker's network traffic. A model that keeps streaming stays alive. Some free endpoints send nothing at all until a large write is finished. From outside, that looks exactly like a hang, so very large single-file writes can still trip the idle limit. The skill tells Claude to split those up.

### Models

The default chain, tried in order, is:

1. `opencode/beam-free`
2. `opencode/deepseek-v4.1-flash-free`
3. `opencode/space-bunny-free`
4. `opencode/mimo-v2.6-flash-free`
5. `opencode/big-pickle`

The free lineup changes often. If these names go stale, check `opencode models | grep free` and set `OC_DELEGATE_MODELS`, or edit `default_models` in `bin/oc-delegate`. This order comes from a benchmark run on 2026-10-18. Each model got two tasks: docstrings plus pytest tests copied from an example file's style, and a rename across five files that had to leave a similarly named function alone. Each task ran twice. `deepseek-v4.1-flash-free` then moved above `space-bunny-free` after the reproducible benchmark under [Development](#model-benchmark): it passed every task there, while `space-bunny-free` wrote failing tests both times.

| Model | Result | Typical time |
| --- | --- | --- |
| `beam-free` | clean on every run | 10–26s |
| `space-bunny-free` | clean on every run (anonymous preview, may disappear) | 22–30s |
| `deepseek-v4.1-flash-free` | clean on every run | 22–50s |
| `mimo-v2.6-flash-free` | clean on every run | 40–220s |
| `big-pickle` | one wrong test assertion | 40–110s |
| `longcat-2.5-preview-free`, `nemotron-3.5-super-vl-free` | slow, wrong test assertions | 60–320s |
| `glm-5.3-flash-free` | "Endpoint is unavailable" on 3 of 4 runs | — |
| `nemotron-3.5-lightning-free` | hung | — |


Models are passed with `-m` because opencode v2.0.x ignored the `model:` field in the agent file.

### Log

Every model attempt appends a tab-separated line to the log: time, `ok` or `fail`, model, duration, repo, files changed or the error, the start of the task, and the check result (empty without `-c`).

```sh
column -ts$'\t' ~/.local/state/oc-delegate.log
```

Use it to check whether delegation actually happens and which models are pulling their weight.

## Privacy and safety

- **Free models may log your prompts and use them for training.** Everything the worker reads in the repo goes to that provider. Don't delegate in confidential repos, and use the approved-repo list in the CLAUDE.md snippet.
- The worker can't read the secret files listed above, but the deny list matches file names only. A secret inside `config.yaml` will still be readable.
- The worker can't touch `.git`. Writing there could plant hooks or a `core.fsmonitor` command that runs on the next git call. opencode's permission rules block it, and with `bwrap`, `.git` is also mounted read-only.
- The worker can edit gitignored files such as `.vscode/`, `node_modules/` or build output. Those edits don't show in `git diff` and can't be reverted by the wrapper, so it lists them under `not in git diff` and the skill tells Claude to check each one.
- Don't put secrets in task prompts.
- Don't add `--auto` or run opencode's default agent from Claude. Claude Code's auto-mode safety check blocks that as creating an unsafe agent, which is why the restricted `cc-worker` agent exists.
- The worker can't run tests or builds. Claude has to verify the result, and the skill tells it to.
- Some projects forbid AI-written contributions. The skill tells Claude not to delegate in those.

## Development

### Tests

```sh
bats test
shellcheck -S warning bin/oc-delegate install.sh test/stub/opencode test/oc-delegate.bats bench/*.sh
```

`test/oc-delegate.bats` runs the wrapper against a fake `opencode` (`test/stub/opencode`). Depending on the model name, the fake edits files and then succeeds, errors, crashes, hangs, keeps printing, runs out of steps, makes malformed tool calls, or breaks a check and fixes it when the session is continued. The tests cover:
- rollback: your uncommitted and staged changes survive, only files the worker edited are reverted (not ones it only read), and odd file names work;
- the final newline: added to text files before the check, left alone in binary files;
- the check loop: passing first time, fixed on a retry in the same session, still failing and falling back, already failing before the run, hanging, and running in the sandbox;
- fallback to the next model;
- the idle, per-model and overall time limits;
- SIGTERM;
- the gitignored-file report and the `.git` sandbox;
- the log.

They need no network and take about a minute. CI runs both commands on every push.

### Model benchmark

`bench/fixture` is a small Python package, and `bench/tasks/` holds four delegation prompts:
- Google-style docstrings for one module;
- pytest tests for an untested module;
- a full test suite for the three untested modules (`numbers.py`, `durations.py`, `table.py`; a few hundred lines of tests);
- a rename across five files that sits next to a similarly named function.

`bench/check.py` grades each result automatically. It checks that pytest passes (in a `bwrap` sandbox without network) and that only the expected files changed. For docstrings it also checks that the code is unchanged apart from the docstrings. For tests it also checks that the new tests catch planted bugs: 4 in `numbers.py`, 6 each in `durations.py` and `table.py`.

```sh
bench/run.sh                                   # every model in the default chain, 2 runs per task
bench/run.sh -n 3 opencode/beam-free           # pick models and runs
bench/run.sh -t tests_all -c "python3 -m pytest -q -p no:cacheprovider"   # with the check loop
```

Each run writes `summary.md`, `results.tsv` and per-run logs to `bench/results/<timestamp>/`. Results from 2026-10-18, 2 runs per task, one model each, no fallback:

| Model | Passed | docstrings | tests | rename | Mean time |
| --- | --- | --- | --- | --- | --- |
| `beam-free` | 5/6 | 2/2 | 2/2 | 1/2 | 16s |
| `space-bunny-free` | 4/6 | 2/2 | 0/2 | 2/2 | 29s |
| `deepseek-v4.1-flash-free` | 6/6 | 2/2 | 2/2 | 2/2 | 26s |
| `big-pickle` | 6/6 | 2/2 | 2/2 | 2/2 | 75s |
| `mimo-v2.6-flash-free` | 6/6 | 2/2 | 2/2 | 2/2 | 99s |

- `space-bunny-free` wrote failing tests both times: it asserted behaviour it couldn't run.
- `beam-free` once produced malformed tool calls. It created junk files with newlines in their names and ran out of steps. The wrapper now treats both as a failed run.

With the check loop (`-c "python3 -m pytest -q -p no:cacheprovider"`, 2026-10-19), `space-bunny-free` passed the tests task 3 of 3. On the full test suite, `beam-free` and `deepseek-v4.1-flash-free` both passed (107–117 tests, all 16 planted bugs caught); `deepseek-v4.1-flash-free` got there after one retry, when its first try had one failing test.

### Skill evaluation

`bench/eval-skill.sh` runs real headless Claude Code sessions (`claude -p`) on the prompts in `skill/evals/evals.json`. Each prompt runs once with the skill and once with Claude told not to delegate. `bench/grade_skill.py` then grades each run:
- Did Claude delegate when it should, and not when it shouldn't?
- Did it check the worker's result?
- Did the outcome pass `bench/check.py`?

The output uses skill-creator's workspace layout, so its `aggregate_benchmark` script and review viewer work on it. It spends real Claude usage, roughly $0.15–0.35 per run for the small evals and more for the large and long-context ones.

`timing.json` also splits each run into phases: Claude's API calls before the first `oc-delegate` call, the call that issues it, and after it, with turns and tokens for each. Input tokens per phase are exact. Output tokens are estimated, since stream-json only carries partial output counts per message. It also records how many files Claude read before delegating.

`docstrings-all-modules-long` repeats the 33-docstring eval with about 60k tokens of earlier-session context (175k characters) added to the system prompt in both configurations (`bench/make-context.py`, pydoc text from the standard library). It shows how the cost of each extra turn grows with context size.

```sh
bench/eval-skill.sh ../opencode-delegate-workspace/iteration-3 5 5   # 5 runs each, 5 at a time
ONLY_EVALS="tests-all" ONLY_RUNS="1 2" bench/eval-skill.sh ../opencode-delegate-workspace/iteration-3   # a subset
python3 -I bench/summarize.py ../opencode-delegate-workspace/iteration-3   # mean ± stddev per eval
```

The sessions count against your own Claude usage limits. When a session hits the limit, the script stops launching new ones and exits 3. Run the same command again after the reset: finished runs are skipped (`FORCE=1` reruns them), and failed ones are flagged in `timing.json` and left out of the summary.

`bench/summarize.py` prints cost, turns, tool calls and outcome checks per eval and configuration as mean ± stddev, and flags a cost difference smaller than the stddev as noise. For runs that delegated, it adds the reads before delegating and the per-phase split. Rounds 1 and 2 ran on a six-module fixture; since round 3 the fixture has eight modules, so the docstring and type-hint numbers aren't comparable across that change.

Results from 2026-10-18 on Opus 5.5, 2 runs per configuration:

| Eval | Delegated with skill | Claude cost, with vs without skill | Claude output tokens, with vs without |
| --- | --- | --- | --- |
| docstrings, one module | 2/2 | $0.29 vs $0.28 (+4%) | 3.4k vs 4.2k |
| tests for one module | 2/2 | $0.25 vs $0.21 (+17%) | 2.5k vs 2.3k |
| docstrings, 19 across six modules | 2/2 | $0.39 vs $0.46 (−15%) | 5.0k vs 9.6k |
| rename across five files | 0/2 (one `perl` command instead) | $0.21 vs $0.19 | 2.2k vs 1.8k |
| bug fix (should stay with Claude) | 0/2 | $0.17 vs $0.17 | 1.1k vs 1.0k |
| tiny edit (should stay with Claude) | 0/2 | $0.16 vs $0.16 | 0.7k vs 0.8k |

Every run passed every outcome check, with or without the skill. Every delegation went to `beam-free`, which succeeded on the first try. The cost column is the catch. A session pays about 20k fresh input tokens up front, and each extra turn re-reads that context. Delegating adds a few turns: loading the skill, running `oc-delegate`, reading the diff, running the tests. That only pays off once the delegated work is several thousand output tokens. Below that, delegating costs slightly more than doing the work directly.

Round 2 tested the changes that came out of round 1:
- the size threshold (roughly 150+ lines, or hand edits across several files);
- one-command `sed`/`perl` edits stay with Claude;
- `deepseek-v4.1-flash-free` moved up the chain.

It also added a type-hints eval across six modules.

| Eval | Delegated with skill | Claude cost, with vs without skill |
| --- | --- | --- |
| docstrings, one module | 0/2 | $0.24 vs $0.37 |
| tests for one module | 0/2 | $0.19 vs $0.23 |
| rename across five files | 0/2 | $0.17 vs $0.20 |
| bug fix, tiny edit | 0/4 | same |
| docstrings, 19 across six modules | 2/2 | $0.46 vs $0.43 (+8%) |
| type hints, 18 functions across six modules | 0/2 | $0.50 vs $0.58 |

- **Small jobs no longer pay overhead.** The skill isn't loaded for small or one-command jobs anymore. On those evals both configurations do the same work, so the remaining cost differences are noise.
- **Delegating a mid-sized job is about cost-neutral.** The 19 docstrings cost −15% in round 1 and +8% in round 2. In the delegated runs, Claude read every file before delegating and then polished the worker's docstrings, which ate the savings.
- **Type hints never triggered the skill.** Picking types takes some judgment, so that may be the right call.
- **Quality is unchanged.** Every behavioural outcome passed in both configurations. In the type-hints eval, the baseline runs also made `LRUCache` generic, which the strict "only annotations" check counts as a code change.

Round 3 (2026-10-19/20) tested the `-c` check loop and the shorter workflow in the skill, on the eight-module fixture, 5 runs per configuration (90 sessions, $38). Costs are mean ± stddev; "noise" means the difference is smaller than the larger stddev.

| Eval | Delegated with skill | Claude cost, with vs without skill | Δ |
| --- | --- | --- | --- |
| docstrings, 33 across eight modules | 5/5 | $0.39 ± 0.03 vs $0.63 ± 0.05 | −39% |
| full test suite for three modules | 5/5 | $0.38 ± 0.05 vs $0.51 ± 0.07 | −25% |
| docstrings, 33, with ~60k tokens of earlier context | 5/5 | $1.08 ± 0.05 vs $1.33 ± 0.13 | −19% |
| type hints, 31 functions across eight modules | 0/5 | $0.60 ± 0.05 vs $0.71 ± 0.10 | −16% |
| docstrings, one module | 0/5 | $0.26 ± 0.02 vs $0.32 ± 0.04 | −19% |
| tests for one module, rename, bug fix, tiny edit | 0/20 | same | noise (−4% to +2%) |

- **Delegating now saves money on large jobs.** All three delegated evals cost clearly less, beyond the noise, and every outcome check still passed. Every delegation ended with the check passing: 14 of 15 on `beam-free` (one after a retry), and once `beam-free` used up its steps and the wrapper fell back to `deepseek-v4.1-flash-free`.
- **Part of that gap isn't delegation.** Two evals that never delegated also cost 16–19% less with the skill. The baseline was told "do all of the work yourself", and it then verified more (14 turns vs 9 for one module of docstrings). Read the delegated savings as an upper bound until a rerun with a neutral baseline; round 4's baseline now only prohibits delegation.
- **Still too many turns.** Delegated runs averaged 9–14 tool calls; the target was 8. Claude no longer reads the files before delegating docstrings, but for the test suite it reads all five source files before it even loads the skill. After delegating, most runs spent 2–3 calls adding the final newline the worker left off every file; the wrapper now adds it itself before the check. Some runs still write their own AST comparison script.
- **Type hints now trigger the skill.** The description names type hints and asks Claude to consult the skill before reading the files. One validation run on the round-3 type-hints eval loaded the skill, delegated to `beam-free`, and finished in 8 tool calls, with the check passing; Claude then fixed three type choices in the diff.

Follow-ups from round 3 (2026-10-20):
- The wrapper now adds a missing final newline to text files the worker edited, before running the check, so Claude no longer spends turns on it.
- The eval baseline no longer says "do all of the work yourself"; it only prohibits delegation.
- The skill description was retuned for type hints and early consultation; the full trigger-optimizer loop is still open.

## Uninstall

```sh
rm ~/.claude/skills/opencode-delegate/SKILL.md ~/.config/opencode/agents/cc-worker.md ~/.local/bin/oc-delegate
rmdir ~/.claude/skills/opencode-delegate
```

Then remove the permission rule and the CLAUDE.md section.

## License

[MIT](LICENSE)
