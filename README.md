# opencode-delegate

A [Claude Code](https://claude.com/claude-code) skill that hands low-judgment grunt work to free [opencode](https://opencode.ai) models, so your Claude usage goes to the parts that need it.

Claude stays in charge. It decides what to delegate, writes the prompt, runs the free model through a sandboxed worker, then reviews the diff and runs the tests itself.

## How it works

```
Claude Code
  └─ opencode-delegate skill        decides a task is grunt work, writes a self-contained prompt
       └─ oc-delegate "task"        wrapper script on your PATH
            └─ opencode run --standalone --agent cc-worker -m <free model>
                 ├─ success → prints model, changed files, worker summary
                 └─ error / 120s silent / 600s total → reverts that model's edits, tries next model
```

- **`skill/SKILL.md`**: tells Claude when to delegate (boilerplate, test scaffolding, docs drafts, fixtures, format conversions, mechanical edits across a few files), when not to (design, tricky bugs, security, anything that needs a shell), and how to review the result.
- **`bin/oc-delegate`**: runs the worker with a fallback chain of free models. If a model fails, hangs or times out, the wrapper reverts only the files that model edited and tries the next one. Your own uncommitted changes are left alone. Every attempt is logged.
- **`opencode/cc-worker.md`**: a locked-down opencode agent. It can list, read and edit files in the current directory, and nothing else: no shell, no grep, no web, no subagents, no paths outside the directory, and no reading or editing `.env*`, `*secret*`, `*credentials*`, `*.pem`, `*.key` or SSH keys.
- **`claude-md-snippet.md`**: a `CLAUDE.md` section that makes delegation Claude's default for grunt work. Without it, Claude rarely picks the skill on its own.

The wrapper refuses to run outside a git repo, so every edit the worker makes shows up in `git diff`.

## Requirements

| Need | Notes |
| --- | --- |
| Claude Code | Any recent version with skills support. |
| [opencode](https://opencode.ai) | Tested with v2.0.32. Needs `opencode run --standalone --format json`. The free OpenCode Zen models work without an API key. |
| `bash`, `git`, `jq` | `jq` parses opencode's JSON event stream. |
| GNU coreutils | `stat -c`, `realpath -m`, `date -Is`. Linux has these. On macOS, install `coreutils` with Homebrew and put its `gnubin` directory first on `PATH`. |
| `~/.local/bin` on `PATH` | Where the installer puts `oc-delegate`. |

Install opencode if you don't have it:

```sh
curl -fsSL https://opencode.ai/install | bash
opencode models | grep -E -- '-free|big-pickle'
```

The second command should list some free models. If none of the default chain's models appear, see [Models](#models).

## Setup

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
model: opencode/deepseek-v4.1-flash-free
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
oc-delegate "task"                                  # default model chain
oc-delegate -m opencode/glm-5.3-flash-free "task"   # one model, no fallback
oc-delegate -m model-a -m model-b "task"            # your own chain
```

### Settings

| Variable | Default | Effect |
| --- | --- | --- |
| `OC_DELEGATE_MODELS` | the chain below | Space-separated model chain, used when no `-m` is given. |
| `OC_DELEGATE_TIMEOUT` | `600` | Seconds before a model run is killed and the next model is tried. |
| `OC_DELEGATE_IDLE` | `120` | Seconds without output before a model counts as hung. |
| `OC_DELEGATE_TAIL` | `40` | Lines of the worker's summary to print. |
| `OC_DELEGATE_LOG` | `~/.local/state/oc-delegate.log` | Where attempts are logged. |

### Models

The default chain, tried in order, is:

1. `opencode/deepseek-v4.1-flash-free`
2. `opencode/glm-5.3-flash-free`
3. `opencode/mimo-v2.6-flash-free`
4. `opencode/big-pickle`

The free lineup changes often. If these names go stale, check `opencode models | grep free` and set `OC_DELEGATE_MODELS`, or edit `default_models` in `bin/oc-delegate`. `nemotron-3-ultra-free` hung with no output in testing, so it's left out.

Models are passed with `-m` because opencode v2.0.x ignored the `model:` field in the agent file.

### Log

Every model attempt appends a tab-separated line to the log: time, `ok` or `fail`, model, duration, repo, files changed or the error, and the start of the task.

```sh
column -ts$'\t' ~/.local/state/oc-delegate.log
```

Use it to check whether delegation actually happens and which models are pulling their weight.

## Privacy and safety

- **Free models may log your prompts and use them for training.** Everything the worker reads in the repo goes to that provider. Don't delegate in confidential repos, and use the approved-repo list in the CLAUDE.md snippet.
- The worker can't read the secret files listed above, but the deny list matches file names only. A secret inside `config.yaml` will still be readable.
- Don't put secrets in task prompts.
- Don't add `--auto` or run opencode's default agent from Claude. Claude Code's auto-mode safety check blocks that as creating an unsafe agent, which is why the restricted `cc-worker` agent exists.
- The worker can't run tests or builds. Claude has to verify the result, and the skill tells it to.
- Some projects forbid AI-written contributions. The skill tells Claude not to delegate in those.

## Uninstall

```sh
rm ~/.claude/skills/opencode-delegate/SKILL.md ~/.config/opencode/agents/cc-worker.md ~/.local/bin/oc-delegate
rmdir ~/.claude/skills/opencode-delegate
```

Then remove the permission rule and the CLAUDE.md section.

## License

[MIT](LICENSE)
