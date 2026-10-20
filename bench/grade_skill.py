"""Grade one skill-eval run: python3 bench/grade_skill.py RUN_DIR EVAL_JSON.

RUN_DIR holds outputs/transcript.jsonl (claude -p stream-json), outputs/changes.diff, checks.json
(bench/check.py) and oc-delegate.log. Writes grading.json and timing.json in skill-creator's format, plus
readable outputs/response.md and outputs/tool-calls.md for the review viewer.

timing.json also splits Claude's API calls into phases: before the first oc-delegate call, the call that
issues it, and after it. Input-side tokens per phase are exact. stream-json only carries partial output
token counts per message, so each phase's output tokens are the total split by its share of visible
output characters.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path


def load_transcript(path):
    events = []
    for line in path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def tool_calls(events):
    calls = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_use":
                calls.append(block)
    return calls


def api_messages(events):
    """API calls in order. stream-json repeats an assistant message once per content block."""
    found = {}
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message", {})
        entry = found.setdefault(message.get("id"), {"usage": {}, "tool_ids": set(), "chars": {}})
        entry["usage"] = message.get("usage") or entry["usage"]
        for i, block in enumerate(message.get("content", [])):
            if block.get("type") == "tool_use":
                entry["tool_ids"].add(block.get("id"))
                text = json.dumps(block.get("input", {}))
            else:
                text = block.get("text") or block.get("thinking") or ""
            entry["chars"][(i, block.get("type"), block.get("id"))] = len(text)
    return list(found.values())


def phase_usage(messages, delegate_id, output_tokens):
    groups = {"before": [], "delegate": [], "after": []}
    phase = "before"
    for message in messages:
        if delegate_id and delegate_id in message["tool_ids"]:
            groups["delegate"].append(message)
            phase = "after"
        else:
            groups[phase].append(message)
    total_chars = sum(sum(m["chars"].values()) for m in messages) or 1
    phases = {}
    for name, group in groups.items():
        usage = [m["usage"] for m in group]
        phases[name] = {
            "turns": len(group),
            "fresh_input_tokens": sum(u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) for u in usage),
            "cache_read_tokens": sum(u.get("cache_read_input_tokens", 0) for u in usage),
            "output_tokens_est": round(output_tokens * sum(sum(m["chars"].values()) for m in group) / total_chars),
        }
    return phases


READ_COMMAND = re.compile(r"^\s*(cat|head|tail|less|nl|bat|sed\s+-n)\b")


def reads_before(calls, changed):
    reads = []
    for call in calls:
        data = call.get("input", {})
        if call.get("name") == "Read":
            reads.append(data.get("file_path", ""))
        elif call.get("name") == "Bash" and READ_COMMAND.search(data.get("command", "")):
            reads.append(data.get("command", ""))
    handed_off = sorted({path for path in changed for read in reads if read.endswith("/" + path) or path in read.split()})
    return reads, handed_off


def describe(call):
    data = call.get("input", {})
    detail = data.get("command") or data.get("file_path") or data.get("skill") or data.get("pattern") or ""
    return f"{call.get('name')}: {' '.join(str(detail).split())[:200]}"


def main():
    run_dir = Path(sys.argv[1])
    spec = json.loads(sys.argv[2])
    outputs = run_dir / "outputs"
    events = load_transcript(outputs / "transcript.jsonl")
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    calls = tool_calls(events)
    errors = sum(1 for e in events if e.get("type") == "user"
                 for b in e.get("message", {}).get("content", []) if isinstance(b, dict) and b.get("is_error"))

    delegate_idx = [i for i, c in enumerate(calls)
                    if c.get("name") == "Bash" and re.search(r"(^|[\s;&|(])oc-delegate(\s|$)", c.get("input", {}).get("command", ""))]
    log = run_dir / "oc-delegate.log"
    attempts = [line.split("\t") for line in log.read_text().splitlines()] if log.exists() else []
    delegated = bool(delegate_idx)
    after = calls[delegate_idx[0] + 1:] if delegated else []
    reviewed = [describe(c) for c in after
                if (c.get("name") == "Bash" and re.search(r"pytest|git (diff|status|show)", c.get("input", {}).get("command", "")))
                or c.get("name") == "Read"]
    answer = result.get("result", "") or ""
    reported = bool(re.search(r"free|opencode|oc-delegate|delegat|beam|bunny|deepseek|mimo|pickle", answer, re.I))
    skill_used = any(c.get("name") == "Skill" and "opencode-delegate" in json.dumps(c.get("input", {})) for c in calls)

    delegation_summary = (f"{len(delegate_idx)} oc-delegate call(s); attempts: "
                          + (", ".join(f"{a[2]} {a[1]} ({a[3]})" + (f" check {a[7]}" if len(a) > 7 and a[7] else "")
                                       for a in attempts if len(a) > 3) or "none logged"))
    expectations = []
    if spec["should_delegate"] is None:
        if delegated:
            expectations += [
                {"text": "if delegated: checked the worker's result itself after delegating", "passed": bool(reviewed),
                 "evidence": "; ".join(reviewed[:4]) if reviewed else "no tests, diff or reads after oc-delegate"},
                {"text": "if delegated: told the user the free model did the work", "passed": reported,
                 "evidence": answer[:300] if answer else "no final answer"},
            ]
    elif spec["should_delegate"]:
        expectations += [
            {"text": "delegated the work to a free model via oc-delegate", "passed": delegated, "evidence": delegation_summary},
            {"text": "checked the worker's result itself after delegating", "passed": delegated and bool(reviewed),
             "evidence": "; ".join(reviewed[:4]) if reviewed else ("did not delegate" if not delegated else "no tests, diff or reads after oc-delegate")},
            {"text": "told the user the free model did the work", "passed": delegated and reported,
             "evidence": answer[:300] if answer else "no final answer"},
        ]
    else:
        expectations.append({"text": "did the work itself without delegating", "passed": not delegated,
                             "evidence": delegation_summary})

    checks = json.loads((run_dir / "checks.json").read_text())["expectations"]
    expectations += checks
    passed = sum(1 for e in expectations if e["passed"])

    usage = Counter()
    for stats in (result.get("modelUsage") or {}).values():
        for key in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"):
            usage[key] += stats.get(key, 0)
    cost = result.get("total_cost_usd", 0.0)
    seconds = round(result.get("duration_ms", 0) / 1000, 1)

    diff = outputs / "changes.diff"
    changed = re.findall(r"^diff --git a/(\S+) b/", diff.read_text(), re.M) if diff.exists() else []
    reads, handed_off = reads_before(calls[:delegate_idx[0]], changed) if delegated else ([], [])
    phases = phase_usage(api_messages(events), calls[delegate_idx[0]].get("id") if delegated else None,
                         usage["outputTokens"])

    counts = Counter(c.get("name") for c in calls)
    grading = {
        "expectations": expectations,
        "summary": {"passed": passed, "failed": len(expectations) - passed, "total": len(expectations),
                    "pass_rate": round(passed / len(expectations), 2)},
        "execution_metrics": {"tool_calls": dict(counts), "total_tool_calls": len(calls),
                              "total_steps": result.get("num_turns", 0), "errors_encountered": errors,
                              "output_chars": len(answer)},
        "user_notes_summary": {"uncertainties": [], "needs_review": [],
                               "workarounds": [f"cost ${cost:.3f}, {usage['outputTokens']} output tokens, "
                                               f"{usage['inputTokens'] + usage['cacheCreationInputTokens']} fresh input tokens, "
                                               f"{usage['cacheReadInputTokens']} cached input tokens; skill loaded: {skill_used}; "
                                               + delegation_summary]},
    }
    timing = {"total_tokens": usage["outputTokens"], "total_duration_seconds": seconds, "cost_usd": cost,
              "input_tokens": usage["inputTokens"], "output_tokens": usage["outputTokens"],
              "cache_read_tokens": usage["cacheReadInputTokens"], "cache_creation_tokens": usage["cacheCreationInputTokens"],
              "error": (result.get("result") or "unknown error")[:200] if result.get("is_error") or not result else None,
              "num_turns": result.get("num_turns", 0), "tool_calls": len(calls), "delegated": delegated,
              "skill_loaded": skill_used, "phases": phases, "reads_before_delegation": len(reads),
              "changed_files_read_before_delegation": handed_off, "reads_before_delegation_detail": reads[:20],
              "delegation_attempts": [{"status": a[1], "model": a[2], "seconds": a[3], "check": a[7] if len(a) > 7 else ""}
                                      for a in attempts if len(a) > 3]}
    (run_dir / "grading.json").write_text(json.dumps(grading, indent=2))
    (run_dir / "timing.json").write_text(json.dumps(timing, indent=2))
    (outputs / "response.md").write_text(answer or "(no final answer)")
    (outputs / "tool-calls.md").write_text("\n".join(f"{i + 1}. {describe(c)}" for i, c in enumerate(calls)) + "\n")


if __name__ == "__main__":
    main()
