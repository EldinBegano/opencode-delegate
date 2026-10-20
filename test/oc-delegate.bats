#!/usr/bin/env bats

setup() {
  export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
  export PATH="$BATS_TEST_DIRNAME/stub:$PATH"
  export OC_DELEGATE_SANDBOX=0
  export OC_DELEGATE_LOG="$BATS_TEST_TMPDIR/log"
  export XDG_CONFIG_HOME="$BATS_TEST_TMPDIR/config"
  export STUB_PIDFILE="$BATS_TEST_TMPDIR/stub.pids"
  wrapper="$BATS_TEST_DIRNAME/../bin/oc-delegate"

  repo="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$repo"
  cd "$repo" || return 1
  git init -q
  git config user.email test@example.com
  git config user.name test
  printf 'a\n' > list.txt
  printf 'o\n' > other.txt
  printf 's\n' > staged.txt
  printf 'ignored.txt\n' > .gitignore
  git add -A
  git commit -qm init
}

teardown() {
  local pid
  if [[ -f "$STUB_PIDFILE" ]]; then
    while read -r pid; do
      kill -9 "$pid" 2>/dev/null || true
    done < "$STUB_PIDFILE"
  fi
}

wait_for() {
  for _ in $(seq 50); do
    eval "$1" && return 0
    sleep 0.2
  done
  return 1
}

@test "refuses to run outside a git repo" {
  cd "$BATS_TEST_TMPDIR"
  run "$wrapper" -m stub/ok "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"not inside a git repo"* ]]
}

@test "prints usage without a task" {
  run "$wrapper" -m stub/ok
  [ "$status" -eq 2 ]
  [[ "$output" == *"usage:"* ]]
}

@test "success reports the model, changed files and summary" {
  export STUB_EDIT=$'list.txt\nnew.txt'
  run "$wrapper" -m stub/ok "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"model: stub/ok"* ]]
  [[ "$output" == *$'M\tlist.txt'* ]]
  [[ "$output" == *$'A\tnew.txt'* ]]
  [[ "$output" == *"---"*"done"* ]]
  [ "$(cat list.txt)" = $'a\nby stub/ok' ]
}

@test "a missing final newline is added before the check runs" {
  export STUB_NOEOL=list.txt
  run "$wrapper" -m stub/ok -c '[ -z "$(tail -c 1 list.txt)" ]' "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"newline: added at end of list.txt"* ]]
  [[ "$output" == *"check: passed"* ]]
  [ "$(tail -c 1 list.txt | od -An -tu1 | tr -d ' ')" = 10 ]
}

@test "binary files without a final newline are left alone" {
  export STUB_NUL=blob.bin
  run "$wrapper" -m stub/ok "task"
  [ "$status" -eq 0 ]
  [ "$(wc -c < blob.bin)" -eq 2 ]
  [[ "$output" != *"newline: added"* ]]
}

@test "failed model's edits to tracked files are reverted" {
  export STUB_EDIT=list.txt
  run "$wrapper" -m stub/error "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"stub/error failed (APIError: rate limited)"* ]]
  [[ "$output" == *"reverted: list.txt"* ]]
  [[ "$output" == *"all models failed"* ]]
  [ "$(cat list.txt)" = a ]
  [ -z "$(git status --porcelain)" ]
}

@test "failed model's new files are removed" {
  export STUB_EDIT=new.txt
  run "$wrapper" -m stub/error "task"
  [ "$status" -eq 1 ]
  [ ! -e new.txt ]
}

@test "rollback keeps the user's uncommitted and staged changes" {
  printf 'user\n' >> other.txt
  printf 'user\n' >> staged.txt
  git add staged.txt
  printf 'u\n' > untracked.txt
  staged_before="$(git diff --cached)"
  export STUB_EDIT=$'other.txt\nstaged.txt\nlist.txt'
  run "$wrapper" -m stub/error "task"
  [ "$status" -eq 1 ]
  [ "$(cat other.txt)" = $'o\nuser' ]
  [ "$(cat staged.txt)" = $'s\nuser' ]
  [ "$(cat list.txt)" = a ]
  [ "$(cat untracked.txt)" = u ]
  [ "$(git diff --cached)" = "$staged_before" ]
}

@test "files the worker didn't report editing are left alone" {
  export STUB_EDIT=list.txt STUB_SILENT_EDIT=other.txt
  run "$wrapper" -m stub/error "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"left alone (not edited by worker): other.txt"* ]]
  [ "$(cat list.txt)" = a ]
  [ "$(cat other.txt)" = $'o\nsilent stub/error' ]
}

@test "files the worker only read are left alone" {
  export STUB_EDIT=list.txt STUB_READ=other.txt STUB_SILENT_EDIT=other.txt
  run "$wrapper" -m stub/error "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"left alone (not edited by worker): other.txt"* ]]
  [ "$(cat list.txt)" = a ]
  [ "$(cat other.txt)" = $'o\nsilent stub/error' ]
}

@test "files edited through apply_patch are reverted" {
  export STUB_PATCH=list.txt
  run "$wrapper" -m stub/error "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"reverted: list.txt"* ]]
  [ "$(cat list.txt)" = a ]
}

@test "paths with spaces and glob characters are restored literally" {
  printf 'x\n' > 'a b.txt'
  printf 'y\n' > '[ab].txt'
  printf 'z\n' > a.txt
  git add -A
  git commit -qm more
  export STUB_EDIT=$'a b.txt\n[ab].txt'
  run "$wrapper" -m stub/error "task"
  [ "$status" -eq 1 ]
  [ "$(cat 'a b.txt')" = x ]
  [ "$(cat '[ab].txt')" = y ]
  [ "$(cat a.txt)" = z ]
}

@test "falls back to the next model and keeps only its edits" {
  export STUB_EDIT=list.txt
  run "$wrapper" -m stub/error -m stub/crash -m stub/ok "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"stub/crash failed (exit 3: boom"* ]]
  [[ "$output" == *"model: stub/ok"* ]]
  [ "$(cat list.txt)" = $'a\nby stub/ok' ]
}

@test "a run without response text counts as failed" {
  export STUB_EDIT=list.txt
  run "$wrapper" -m stub/notext "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"failed (no response text)"* ]]
  [ "$(cat list.txt)" = a ]
}

@test "a run that used up its step limit counts as failed" {
  export STUB_EDIT=list.txt
  run "$wrapper" -m stub/maxsteps -m stub/ok "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"stub/maxsteps failed (used all 40 steps)"* ]]
  [ "$(cat list.txt)" = $'a\nby stub/ok' ]
}

@test "the step limit is read from the cc-worker agent file" {
  mkdir -p "$BATS_TEST_TMPDIR/config/opencode/agents"
  printf -- '---\nsteps: 100\n---\n' > "$BATS_TEST_TMPDIR/config/opencode/agents/cc-worker.md"
  export STUB_EDIT=list.txt XDG_CONFIG_HOME="$BATS_TEST_TMPDIR/config"
  run "$wrapper" -m stub/maxsteps "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"model: stub/maxsteps"* ]]
}

@test "file names with control characters count as malformed tool calls and are removed" {
  export STUB_EDIT=list.txt
  run "$wrapper" -m stub/malformed "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"stub/malformed failed (malformed tool calls: file names with control characters)"* ]]
  [ "$(cat list.txt)" = a ]
  [ -z "$(git status --porcelain)" ]
}

@test "OC_DELEGATE_MODELS sets the chain when no -m is given" {
  export OC_DELEGATE_MODELS="stub/error stub/ok"
  run "$wrapper" "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"stub/error failed"* ]]
  [[ "$output" == *"model: stub/ok"* ]]
}

@test "a silent model is stopped after the idle limit and reverted" {
  export STUB_EDIT=list.txt OC_DELEGATE_IDLE=3
  run "$wrapper" -m stub/silent -m stub/ok "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"stub/silent failed (no output or network traffic for 3s)"* ]]
  [ "$(cat list.txt)" = $'a\nby stub/ok' ]
}

@test "a model that keeps printing is stopped at the per-model limit" {
  export STUB_EDIT=list.txt OC_DELEGATE_TIMEOUT=3
  run "$wrapper" -m stub/chatty -m stub/ok "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"stub/chatty failed (timed out after 3s)"* ]]
  [ "$(cat list.txt)" = $'a\nby stub/ok' ]
}

@test "the overall limit stops the chain" {
  export STUB_EDIT=list.txt OC_DELEGATE_TOTAL=4
  run "$wrapper" -m stub/chatty -m stub/ok "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"stub/chatty failed (timed out after 4s)"* ]]
  [[ "$output" == *"4s overall limit reached before trying stub/ok"* ]]
  [ "$(cat list.txt)" = a ]
}

@test "stopped workers leave no processes behind" {
  export STUB_EDIT=list.txt OC_DELEGATE_IDLE=3
  run "$wrapper" -m stub/silent "task"
  [ "$status" -eq 1 ]
  while read -r pid; do
    ! kill -0 "$pid" 2>/dev/null
  done < "$STUB_PIDFILE"
}

@test "SIGTERM stops the worker, reverts its edits and exits 130" {
  export STUB_EDIT=list.txt
  "$wrapper" -m stub/silent "task" > "$BATS_TEST_TMPDIR/out" 2>&1 3>&- &
  pid=$!
  wait_for "grep -q 'by stub/silent' list.txt"
  kill -TERM "$pid"
  status=0
  wait "$pid" || status=$?
  [ "$status" -eq 130 ]
  grep -q "interrupted" "$BATS_TEST_TMPDIR/out"
  [ "$(cat list.txt)" = a ]
  while read -r stub; do
    ! kill -0 "$stub" 2>/dev/null
  done < "$STUB_PIDFILE"
}

@test "edits to gitignored files are listed, not hidden" {
  printf 'orig\n' > ignored.txt
  export STUB_EDIT=$'ignored.txt\nlist.txt'
  run "$wrapper" -m stub/ok "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"not in git diff (gitignored or .git):"*"ignored.txt"* ]]
}

@test "gitignored edits of a failed model are reported as not reverted" {
  printf 'orig\n' > ignored.txt
  export STUB_EDIT=ignored.txt
  run "$wrapper" -m stub/error "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"not reverted (gitignored or .git): ignored.txt"* ]]
}

@test "edits inside .git are listed when running unsandboxed" {
  run "$wrapper" -m stub/dotgit "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"not in git diff (gitignored or .git):"*".git/description"* ]]
}

@test "the bwrap sandbox makes .git read-only" {
  bwrap --ro-bind / / true 2>/dev/null || skip "bwrap not usable here"
  before="$(cat .git/description)"
  OC_DELEGATE_SANDBOX=1 run "$wrapper" -m stub/dotgit "task"
  [ "$status" -eq 0 ]
  [ "$(cat .git/description)" = "$before" ]
}

@test "every attempt is logged" {
  export STUB_EDIT=list.txt
  run "$wrapper" -m stub/error -m stub/ok "task text"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$OC_DELEGATE_LOG")" -eq 2 ]
  [ "$(cut -f2,3 "$OC_DELEGATE_LOG" | head -n 1)" = $'fail\tstub/error' ]
  [ "$(cut -f2,3,6,7 "$OC_DELEGATE_LOG" | tail -n 1)" = $'ok\tstub/ok\t1 files changed\ttask text' ]
}

@test "rejects a retry count that isn't a number" {
  run "$wrapper" -m stub/ok -r x "task"
  [ "$status" -eq 2 ]
  [[ "$output" == *"retries must be a whole number"* ]]
}

@test "a check that passes the first time runs the worker once" {
  export STUB_EDIT=list.txt
  run "$wrapper" -m stub/ok -c '! grep broken list.txt' "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *$'M\tlist.txt\ncheck: passed\n---'* ]]
  [ "$(wc -l < "$STUB_PIDFILE")" -eq 1 ]
}

@test "a failing check goes back to the same session and the fix is kept" {
  export STUB_EDIT=list.txt STUB_PROMPTS="$BATS_TEST_TMPDIR/prompts"
  run "$wrapper" -m stub/fixer -c '! grep broken list.txt' "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"check failed (broken stub/fixer); retry 1 of 2"* ]]
  [[ "$output" == *"check: passed after 1 retry"* ]]
  [ "$(cat list.txt)" = $'a\nfixed stub/fixer' ]
  [ "$(wc -l < "$STUB_PIDFILE")" -eq 2 ]
  [[ "$(cat "$STUB_PROMPTS")" == $'task\n--\nThe check `! grep broken list.txt` failed:\nbroken stub/fixer\nFix the cause.'* ]]
  [ "$(cut -f8 "$OC_DELEGATE_LOG")" = "passed after 1 retry" ]
}

@test "a check that keeps failing reverts the model and tries the next one" {
  export STUB_EDIT=list.txt OC_DELEGATE_CHECK='! grep broken list.txt' OC_DELEGATE_RETRIES=1
  run "$wrapper" -m stub/broken -m stub/ok "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"stub/broken failed (check failed after 1 retry: broken stub/broken)"* ]]
  [[ "$output" == *"reverted: list.txt"* ]]
  [[ "$output" == *"model: stub/ok"* ]]
  [[ "$output" == *"check: passed"* ]]
  [ "$(cat list.txt)" = $'a\nby stub/ok' ]
  [ "$(wc -l < "$STUB_PIDFILE")" -eq 3 ]
}

@test "a check that already fails before the run is skipped" {
  printf 'broken\n' >> other.txt
  export STUB_EDIT=list.txt
  run "$wrapper" -m stub/broken -c '! grep broken other.txt' "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"check: already failing before the run; skipped (broken)"* ]]
  [ "$(cat list.txt)" = $'a\nbroken stub/broken' ]
  [ "$(wc -l < "$STUB_PIDFILE")" -eq 1 ]
}

@test "a hanging check is killed at OC_DELEGATE_CHECK_TIMEOUT" {
  export STUB_EDIT=list.txt OC_DELEGATE_CHECK_TIMEOUT=2
  pidfile="$BATS_TEST_TMPDIR/check.pid"
  run "$wrapper" -m stub/ok -r 0 -c "if grep -q by list.txt; then echo \$\$ > '$pidfile'; exec sleep 600; fi" "task"
  [ "$status" -eq 1 ]
  [[ "$output" == *"stub/ok failed (check failed: check timed out after 2s)"* ]]
  [ "$(cat list.txt)" = a ]
  ! kill -0 "$(cat "$pidfile")" 2>/dev/null
}

@test "the check runs in the bwrap sandbox with .git read-only" {
  bwrap --ro-bind / / --unshare-net true 2>/dev/null || skip "bwrap not usable here"
  export STUB_EDIT=list.txt
  OC_DELEGATE_SANDBOX=1 run "$wrapper" -m stub/ok -c '! touch .git/probe 2>/dev/null && touch cache.txt' "task"
  [ "$status" -eq 0 ]
  [[ "$output" == *"check: passed"* ]]
  [ ! -e .git/probe ]
  [ -e cache.txt ]
}

@test "SIGTERM during the check stops it and reverts the worker's edits" {
  export STUB_EDIT=list.txt
  pidfile="$BATS_TEST_TMPDIR/check.pid"
  "$wrapper" -m stub/ok -c "if grep -q by list.txt; then echo \$\$ > '$pidfile'; exec sleep 600; fi" "task" \
    > "$BATS_TEST_TMPDIR/out" 2>&1 3>&- &
  pid=$!
  wait_for "[ -s '$pidfile' ]"
  kill -TERM "$pid"
  status=0
  wait "$pid" || status=$?
  [ "$status" -eq 130 ]
  [ "$(cat list.txt)" = a ]
  [ "$(cut -f2,8 "$OC_DELEGATE_LOG")" = $'fail\t' ]
  ! kill -0 "$(cat "$pidfile")" 2>/dev/null
}
