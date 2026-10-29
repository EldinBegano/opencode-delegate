# Development

The tests, the model benchmark and the skill evals behind the defaults in the [README](../README.md).

## Tests

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

## Model choice

The default model order in `bin/oc-delegate` comes from a benchmark run on 2026-10-18. Each model got two tasks: docstrings plus pytest tests copied from an example file's style, and a rename across five files that had to leave a similarly named function alone. Each task ran twice. `deepseek-v4.1-flash-free` then moved above `space-bunny-free` after the reproducible benchmark below ([Model benchmark](#model-benchmark)): it passed every task there, while `space-bunny-free` wrote failing tests both times.

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

## Model benchmark

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

## Skill evaluation

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
