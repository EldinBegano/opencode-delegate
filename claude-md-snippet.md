# opencode delegation
- Before writing boilerplate, test scaffolding, docstrings/README/changelog drafts, fixture/data files, format conversions or mechanical edits across a few known files, delegate via the `opencode-delegate` skill (`oc-delegate`) instead of writing it yourself. Skip only when the skill's "do it yourself" list applies.
- Repos approved for free models: (none yet). Before the first delegation in any other repo, ask the user once whether its contents may go to free models, and add it to this list if they say yes.
- Every run is logged to `~/.local/state/oc-delegate.log` (TSV: time, ok/fail, model, duration, repo, result, task).
