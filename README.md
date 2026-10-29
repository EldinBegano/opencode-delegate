# opencode-delegate

A [Claude Code](https://claude.com/claude-code) skill that hands low-judgment grunt work to free [opencode](https://opencode.ai) models, so your Claude usage goes to the parts that need it.

Claude stays in charge. It decides what to delegate, writes the prompt, runs the free model through a sandboxed worker, then reviews the diff and runs the tests itself.

![Claude Code loading the skill, delegating 33 docstrings to a free model with the tests as the check, then reviewing the diff](docs/demo.gif)

A real Claude Code session on the benchmark fixture, with the waits cut out. It cost $0.31 of Claude usage. The same task averaged $0.63 without the skill.

## What you get

- **`skill/SKILL.md`**: tells Claude when to delegate (boilerplate, tests, docs, fixtures, edits across several files), when not to (design, tricky bugs, security), and how to review the result.
- **`bin/oc-delegate`**: runs the worker with a fallback chain of free models. If a model fails or hangs, only the files it edited are reverted and the next model is tried. Your own uncommitted changes are left alone.
- **`opencode/cc-worker.md`**: a locked-down opencode agent. It can read and edit files in the repo, and nothing else: no shell, no web, no `.git`, `.env*`, keys or credential files.
- **`claude-md-snippet.md`**: a `CLAUDE.md` section that makes delegation Claude's default for grunt work. Without it, Claude rarely picks the skill on its own.

## Requirements

| Need | Notes |
| --- | --- |
| Claude Code | Any recent version with skills support. |
| [opencode](https://opencode.ai) | Tested with v2.0.32 and v2.1.3. The free OpenCode Zen models work without an API key. |
| `bash`, `git`, `jq` | |
| GNU coreutils | Linux has these. On macOS, install `coreutils` with Homebrew and put its `gnubin` directory first on `PATH`. |
| `~/.local/bin` on `PATH` | Where the installer puts `oc-delegate`. |
| `bwrap` (optional, Linux) | [bubblewrap](https://github.com/containers/bubblewrap) sandboxes the worker's file writes to the repo. Recommended. |

Install opencode if you don't have it, then check that it lists free models:

```sh
curl -fsSL https://opencode.ai/install | bash
opencode models | grep -E -- '-free|big-pickle'
```

## Install

### Let Claude Code do it

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

Start a new Claude Code session afterwards so the skill and the `CLAUDE.md` section load.

### Manually

1. Clone and install:

   ```sh
   git clone https://github.com/EldinBegano/opencode-delegate.git
   cd opencode-delegate
   ./install.sh
   ```

   The installer symlinks the skill, the worker agent and `oc-delegate` into `~/.claude/skills/`, `~/.config/opencode/agents/` and `~/.local/bin/`, so `git pull` updates them. Use `./install.sh --copy` to copy them instead. Existing files that differ are backed up first.

2. Let Claude run the wrapper without asking each time. Add this to `~/.claude/settings.json`, merging it into your existing `permissions.allow` list:

   ```json
   {
     "permissions": {
       "allow": ["Bash(oc-delegate:*)"]
     }
   }
   ```

3. Paste [`claude-md-snippet.md`](claude-md-snippet.md) into `~/.claude/CLAUDE.md`. Don't skip this: with only the skill installed, Claude tends to write grunt work itself. The snippet keeps a list of repos you've approved for free models. Claude asks you once before the first delegation in a new repo.

4. Smoke test:

   ```sh
   tmp=$(mktemp -d) && cd "$tmp" && git init -q
   printf 'a\nb\n' > list.txt && git add . && git commit -qm init
   oc-delegate "Append a line containing exactly 'c' to list.txt. Change no other file."
   git diff
   ```

   You should see `model: opencode/...`, `M list.txt`, and a diff that adds `c`.

## Usage

Most of the time you don't call anything. Claude delegates big grunt jobs, such as docstrings or tests across several modules, and tells you what the free model did and what it checked. Small jobs stay with Claude on purpose, because delegating them costs more than it saves.

To force it, say "delegate this", "use opencode" or "use the free model", or type `/opencode-delegate`.

You can also run the wrapper yourself inside any git repo:

```sh
oc-delegate "task"                                       # default model chain
oc-delegate -m opencode/deepseek-v4.1-flash-free "task"   # one model, no fallback
oc-delegate -c "pytest -q" "task"                        # run a check after the worker
```

With `-c`, a failing check goes back to the worker to fix, up to `-r` times (default 2). If it still fails, that model's edits are reverted and the next model is tried. If the check already fails before the run, it's skipped.

### Settings

| Variable | Default | Effect |
| --- | --- | --- |
| `OC_DELEGATE_MODELS` | the chain below | Space-separated model chain, used when no `-m` is given. |
| `OC_DELEGATE_TIMEOUT` | `300` | Seconds before a model run is killed and the next model is tried. |
| `OC_DELEGATE_IDLE` | `180` | Seconds with no output and no network traffic before a model counts as hung. |
| `OC_DELEGATE_TOTAL` | `540` | Seconds for the whole run. Keep it below Claude Code's 600s Bash timeout. |
| `OC_DELEGATE_CHECK` | none | Check command, used when no `-c` is given. |
| `OC_DELEGATE_RETRIES` | `2` | Check retries per model, used when no `-r` is given. |
| `OC_DELEGATE_CHECK_TIMEOUT` | `120` | Seconds per check run. |
| `OC_DELEGATE_SANDBOX` | `1` | Set to `0` to run without `bwrap`. |
| `OC_DELEGATE_TAIL` | `40` | Lines of the worker's summary to print. |
| `OC_DELEGATE_LOG` | `~/.local/state/oc-delegate.log` | Log of every model attempt. View it with `column -ts$'\t' ~/.local/state/oc-delegate.log`. |

### Models

The default chain is `beam-free` → `deepseek-v4.1-flash-free` → `space-bunny-free` → `mimo-v2.6-flash-free` → `big-pickle`, all under `opencode/`. The free lineup changes often. If these go stale, check `opencode models | grep free` and set `OC_DELEGATE_MODELS`. How the order was picked: [docs/development.md](docs/development.md#model-choice).

## Privacy and safety

- **Free models may log your prompts and use them for training.** Everything the worker reads in the repo goes to that provider. Don't delegate in confidential repos.
- The worker's deny list matches file names only. A secret inside `config.yaml` is still readable.
- The worker can't touch `.git`. With `bwrap`, `.git` is also mounted read-only.
- The worker can edit gitignored files, which `git diff` doesn't show. The wrapper lists them under `not in git diff`.
- The worker can't run tests or builds. Claude verifies the result.
- Don't put secrets in task prompts.

## Development

Run `bats test` (no network, about a minute). The tests, model benchmark and skill evals are described in [docs/development.md](docs/development.md).

## Uninstall

```sh
rm ~/.claude/skills/opencode-delegate/SKILL.md ~/.config/opencode/agents/cc-worker.md ~/.local/bin/oc-delegate
rmdir ~/.claude/skills/opencode-delegate
```

Then remove the permission rule and the `CLAUDE.md` section.

## License

[MIT](LICENSE)
