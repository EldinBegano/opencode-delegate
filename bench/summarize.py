"""Summarize a skill-eval iteration: python3 -I bench/summarize.py ITERATION_DIR.

Reads eval-*/<config>/run-*/{timing,checks}.json written by bench/eval-skill.sh and prints Markdown tables,
also saved as ITERATION_DIR/summary.md:
- cost, turns, tool calls and outcome checks (checks.json) per eval and configuration, as mean ± stddev, with the cost delta
  flagged as noise when it is smaller than the larger of the two stddevs;
- for runs that delegated: reads before delegating and the per-phase split of turns and tokens.
"""

import json
import statistics
import sys
from pathlib import Path

CONFIGS = ("with_skill", "without_skill")


def load(iteration):
    runs = {}
    for timing_path in sorted(iteration.glob("eval-*/*/run-*/timing.json")):
        run = timing_path.parent
        if json.loads(timing_path.read_text()).get("error"):
            print(f"skipped, session failed: {run.relative_to(iteration)}", file=sys.stderr)
            continue
        checks = json.loads((run / "checks.json").read_text())["expectations"]
        runs.setdefault(run.parent.parent.name.removeprefix("eval-"), {}).setdefault(run.parent.name, []).append(
            {"timing": json.loads(timing_path.read_text()), "pass_rate": sum(c["passed"] for c in checks) / len(checks)})
    return runs


def stats(values):
    if not values:
        return None, None
    return statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0.0


def fmt(values, digits=0, prefix=""):
    mean, sd = stats(values)
    if mean is None:
        return "—"
    return f"{prefix}{mean:.{digits}f} ± {sd:.{digits}f}"


def cost_row(name, configs):
    costs = {c: [r["timing"]["cost_usd"] for r in configs.get(c, [])] for c in CONFIGS}
    (with_mean, with_sd), (without_mean, without_sd) = stats(costs["with_skill"]), stats(costs["without_skill"])
    delta = verdict = "—"
    if with_mean is not None and without_mean:
        delta = f"{(with_mean - without_mean) / without_mean:+.0%}"
        verdict = "noise" if abs(with_mean - without_mean) < max(with_sd, without_sd) else "real"

    def both(key, digits=0):
        return " / ".join(fmt([r["timing"].get(key, 0) for r in configs.get(c, [])], digits) for c in CONFIGS)

    pass_rates = " / ".join(fmt([r["pass_rate"] for r in configs.get(c, [])], 2) for c in CONFIGS)
    delegated = sum(r["timing"].get("delegated", False) for r in configs.get("with_skill", []))
    n = "/".join(str(len(configs.get(c, []))) for c in CONFIGS)
    return (f"| {name} | {n} | {fmt(costs['with_skill'], 3, '$')} | {fmt(costs['without_skill'], 3, '$')} | {delta} "
            f"| {verdict} | {both('num_turns')} | {both('tool_calls')} | {pass_rates} "
            f"| {delegated}/{len(configs.get('with_skill', []))} |")


def phase_rows(name, configs):
    runs = [r["timing"] for r in configs.get("with_skill", []) if r["timing"].get("delegated") and "phases" in r["timing"]]
    if not runs:
        return []
    rows = []
    for phase in ("before", "delegate", "after"):
        values = [run["phases"][phase] for run in runs]
        rows.append(f"| {name} | {phase} | {fmt([v['turns'] for v in values], 1)} "
                    f"| {fmt([v['fresh_input_tokens'] for v in values])} | {fmt([v['cache_read_tokens'] for v in values])} "
                    f"| {fmt([v['output_tokens_est'] for v in values])} |")
    reads = fmt([run["reads_before_delegation"] for run in runs], 1)
    handed = sum(bool(run["changed_files_read_before_delegation"]) for run in runs)
    calls = fmt([run["tool_calls"] for run in runs], 1)
    return rows, f"| {name} | {len(runs)} | {calls} | {reads} | {handed}/{len(runs)} |"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: summarize.py ITERATION_DIR")
    iteration = Path(sys.argv[1])
    runs = load(iteration)
    lines = [
        "| Eval | Runs (with/without) | Cost with skill | Cost without | Δ cost | Δ vs stddev | Turns (with / without) "
        "| Tool calls (with / without) | Outcome checks passed (with / without) | Delegated |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [cost_row(name, configs) for name, configs in sorted(runs.items())]
    phases, delegation = [], []
    for name, configs in sorted(runs.items()):
        result = phase_rows(name, configs)
        if result:
            phases += result[0]
            delegation.append(result[1])
    if delegation:
        lines += ["", "Delegated runs:", "",
                  "| Eval | Runs | Tool calls | Reads before oc-delegate | Runs that read a changed file first |",
                  "| --- | --- | --- | --- | --- |", *delegation,
                  "", "Per phase, delegated runs (output tokens estimated from visible output characters):", "",
                  "| Eval | Phase | API calls | Fresh input tokens | Cached input tokens | Output tokens |",
                  "| --- | --- | --- | --- | --- | --- |", *phases]
    text = "\n".join(lines) + "\n"
    (iteration / "summary.md").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
