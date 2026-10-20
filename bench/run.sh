#!/usr/bin/env bash
set -uo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
wrapper="$here/../bin/oc-delegate"

runs=2
tasks="docstrings tests rename"
check_args=()
while getopts n:t:c: opt; do
  case "$opt" in
    n) runs="$OPTARG" ;;
    t) tasks="$OPTARG" ;;
    c) check_args=(-c "$OPTARG") ;;
    *) echo "usage: bench/run.sh [-n RUNS] [-t \"TASK...\"] [-c \"CHECK\"] [MODEL...]" >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))

if [[ $# -gt 0 ]]; then
  models=("$@")
else
  mapfile -t models < <(sed -n '/^default_models=(/,/^)/{s/^ *//;/^default_models\|^)/d;p}' "$wrapper")
fi

out="$here/results/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"
printf 'model\ttask\trun\tseconds\tdelegate\tchecks\tpassed\tfailed_checks\n' > "$out/results.tsv"

bench_model() {
  local model="$1" slug="${1//\//_}" task run repo start seconds code result checks failed passed
  for task in $tasks; do
    for run in $(seq "$runs"); do
      repo="$(mktemp -d)/repo"
      "$here/make-repo.sh" "$task" "$repo"
      start=$SECONDS
      (cd "$repo" && OC_DELEGATE_LOG="$out/oc-delegate.log" "$wrapper" -m "$model" ${check_args[@]+"${check_args[@]}"} "$(cat "$here/tasks/$task.txt")") \
        > "$out/$slug-$task-$run.log" 2>&1
      code=$?
      seconds=$((SECONDS - start))
      result="$(python3 -I "$here/check.py" "$task" "$repo")"
      printf '%s\n' "$result" > "$out/$slug-$task-$run.json"
      checks="$(jq -r '"\([.expectations[] | select(.passed)] | length)/\(.expectations | length)"' <<< "$result")"
      failed="$(jq -r '[.expectations[] | select(.passed | not) | .text] | join("; ")' <<< "$result")"
      passed=no
      [[ $code -eq 0 && -z "$failed" ]] && passed=yes
      [[ $code -ne 0 ]] && failed="oc-delegate exit $code: $(grep -m1 'failed (' "$out/$slug-$task-$run.log" | sed 's/^oc-delegate: //')"
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$model" "$task" "$run" "$seconds" "$code" "$checks" "$passed" "$failed" >> "$out/results.tsv"
      rm -rf -- "$(dirname -- "$repo")"
    done
  done
}

echo "benchmarking ${#models[@]} models x ($tasks) x $runs runs -> $out" >&2
for model in "${models[@]}"; do
  bench_model "$model" &
done
wait

awk -F'\t' -v tasks="$tasks" '
  NR == 1 { next }
  { key = $1; n[key]++; t[key] += $4; if ($7 == "yes") ok[key]++; if (!(key in order)) { order[key] = ++m; names[m] = key } }
  { tk = $1 SUBSEP $2; tn[tk]++; if ($7 == "yes") tok[tk]++ }
  END {
    nt = split(tasks, task, " ")
    head = "| Model | Passed |"; rule = "| --- | --- |"
    for (j = 1; j <= nt; j++) { head = head " " task[j] " |"; rule = rule " --- |" }
    print head " Mean time |"
    print rule " --- |"
    for (i = 1; i <= m; i++) {
      k = names[i]
      line = sprintf("| `%s` | %d/%d |", k, ok[k], n[k])
      for (j = 1; j <= nt; j++) line = line sprintf(" %d/%d |", tok[k, task[j]], tn[k, task[j]])
      printf "%s %ds |\n", line, t[k] / n[k]
    }
  }' "$out/results.tsv" > "$out/summary.md"
cat "$out/summary.md"
echo "details: $out/results.tsv" >&2
