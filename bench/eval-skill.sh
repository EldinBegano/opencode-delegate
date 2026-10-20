#!/usr/bin/env bash
set -uo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: bench/eval-skill.sh ITERATION_DIR [RUNS] [PARALLEL]" >&2
  exit 2
fi
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
evals="$here/../skill/evals/evals.json"
iter="$(realpath -m -- "$1")"
runs="${2:-5}"
parallel="${3:-5}"
repos="${TMPDIR:-/tmp}/skill-eval-repos"

approved="This repository is a throwaway benchmark fixture. It is approved for delegation to free opencode models, as if it were listed as approved in the opencode-delegate memory."
# Only prohibit delegation; don't tell the baseline to "do all the work yourself", which
# made it verify more than an unconstrained session would.
baseline="Do not use the opencode-delegate skill or oc-delegate in this session."

one_run() {
  local spec="$1" config="$2" run="$3" name task long dir repo extra
  local -a disallow=()
  name="$(jq -r .name <<< "$spec")"
  task="$(jq -r .task <<< "$spec")"
  long="$(jq -r '.long_context // false' <<< "$spec")"
  dir="$iter/eval-$name/$config/run-$run"
  repo="$repos/$name-$config-$run/textkit"
  if [[ -z "${FORCE:-}" ]] && jq -e '.error == null' "$dir/timing.json" >/dev/null 2>&1; then
    echo "skip: $name $config run-$run (already done; FORCE=1 reruns it)" >&2
    return
  fi
  rm -rf -- "$dir" "$(dirname -- "$repo")"
  mkdir -p -- "$dir/outputs"
  "$here/make-repo.sh" "$task" "$repo"
  if [[ "$config" == with_skill ]]; then
    extra="$approved"
  else
    extra="$baseline"
    disallow=(--disallowedTools "Bash(oc-delegate:*)")
  fi
  jq -r .prompt <<< "$spec" > "$dir/prompt.txt"
  printf '%s\n' "$extra" > "$dir/system-append.txt"
  if [[ "$long" == true ]]; then
    printf '\n' >> "$dir/system-append.txt"
    cat -- "$context" >> "$dir/system-append.txt"
  fi
  (cd -- "$repo" && OC_DELEGATE_LOG="$dir/oc-delegate.log" timeout 1200 claude -p \
    --output-format stream-json --verbose --no-session-persistence --max-budget-usd 5 \
    --permission-mode acceptEdits \
    --append-system-prompt-file "$dir/system-append.txt" \
    "${disallow[@]}" \
    --allowedTools "Bash(oc-delegate:*)" "Bash(git:*)" "Bash(python3:*)" "Bash(python:*)" "Bash(pytest:*)" "Bash(perl:*)" "Bash(sed:*)" \
      "Bash(wc:*)" "Bash(ls:*)" "Skill" "Read" "Edit" "Write" "Glob" "Grep" \
    < "$dir/prompt.txt" > "$dir/outputs/transcript.jsonl" 2> "$dir/outputs/stderr.txt")
  if jq -e 'select(.type == "result" and .is_error and (.result | test("limit")))' "$dir/outputs/transcript.jsonl" >/dev/null 2>&1; then
    jq -r 'select(.type == "result") | .result' "$dir/outputs/transcript.jsonl" > "$iter/limit-hit"
  fi
  python3 -I "$here/check.py" "$task" "$repo" > "$dir/checks.json"
  git -C "$repo" add -N . && git -C "$repo" diff > "$dir/outputs/changes.diff"
  python3 -I "$here/grade_skill.py" "$dir" "$spec"
  echo "done: $name $config run-$run ($(jq -r '.summary | "\(.passed)/\(.total)"' "$dir/grading.json"))" >&2
}

mkdir -p -- "$iter" "$repos"
context="$iter/long-context.txt"
[[ -f "$context" ]] || python3 -I "$here/make-context.py" "$context"
count="$(jq '.evals | length' "$evals")"
for i in $(seq 0 $((count - 1))); do
  spec="$(jq -c ".evals[$i]" "$evals")"
  name="$(jq -r .name <<< "$spec")"
  mkdir -p -- "$iter/eval-$name"
  jq '{eval_id: .id, eval_name: .name, prompt: .prompt, assertions: .expectations}' <<< "$spec" > "$iter/eval-$name/eval_metadata.json"
done

rm -f -- "$iter/limit-hit"
running=0
for run in $(seq "$runs"); do
  if [[ -n "${ONLY_RUNS:-}" && " $ONLY_RUNS " != *" $run "* ]]; then
    continue
  fi
  for i in $(seq 0 $((count - 1))); do
    spec="$(jq -c ".evals[$i]" "$evals")"
    if [[ -n "${ONLY_EVALS:-}" && " $ONLY_EVALS " != *" $(jq -r .name <<< "$spec") "* ]]; then
      continue
    fi
    for config in ${CONFIGS:-with_skill without_skill}; do
      [[ -f "$iter/limit-hit" ]] && break 3
      one_run "$spec" "$config" "$run" &
      running=$((running + 1))
      if (( running >= parallel )); then
        wait -n
        running=$((running - 1))
      fi
    done
  done
done
wait
if [[ -f "$iter/limit-hit" ]]; then
  echo "stopped: $(cat -- "$iter/limit-hit"). Run the same command again after that; finished runs are skipped." >&2
  exit 3
fi
