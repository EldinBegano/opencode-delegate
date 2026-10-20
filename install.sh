#!/usr/bin/env bash
set -euo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
claude_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
opencode_dir="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
bin_dir="$HOME/.local/bin"

mode="link"
case "${1:-}" in
  "") ;;
  --copy) mode=copy ;;
  *) echo "usage: ./install.sh [--copy]" >&2; exit 2 ;;
esac

missing=()
for cmd in git jq opencode; do
  command -v "$cmd" >/dev/null || missing+=("$cmd")
done
if ! stat -c %s "$repo/install.sh" >/dev/null 2>&1 || ! realpath -m / >/dev/null 2>&1; then
  missing+=("GNU coreutils (stat -c, realpath -m)")
fi
if [[ ${#missing[@]} -gt 0 ]]; then
  printf 'missing: %s\n' "${missing[@]}" >&2
  exit 1
fi

links_to() {
  [[ -L "$2" && "$(readlink -- "$2")" == "$1" ]]
}

up_to_date() {
  if [[ $mode == link ]]; then
    links_to "$1" "$2"
  else
    [[ -f "$2" && ! -L "$2" ]] && cmp -s -- "$1" "$2"
  fi
}

place() {
  local src="$repo/$1" dest="$2" backup
  mkdir -p -- "$(dirname -- "$dest")"
  if up_to_date "$src" "$dest"; then
    echo "up to date  $dest"
    return
  fi
  if links_to "$src" "$dest" || cmp -s -- "$src" "$dest" 2>/dev/null; then
    rm -- "$dest"
  elif [[ -e "$dest" || -L "$dest" ]]; then
    backup="$dest.bak.$(date +%Y%m%d%H%M%S)"
    mv -- "$dest" "$backup"
    echo "backed up   $backup"
  fi
  if [[ $mode == link ]]; then
    ln -s -- "$src" "$dest"
    echo "linked      $dest"
  else
    cp -- "$src" "$dest"
    echo "copied      $dest"
  fi
}

place skill/SKILL.md "$claude_dir/skills/opencode-delegate/SKILL.md"
place opencode/cc-worker.md "$opencode_dir/agents/cc-worker.md"
place bin/oc-delegate "$bin_dir/oc-delegate"

[[ ":$PATH:" == *":$bin_dir:"* ]] || echo "warning: $bin_dir is not on PATH" >&2
command -v bwrap >/dev/null || echo "note: bwrap not found; the worker will run without the filesystem sandbox" >&2

cat <<EOF

Next steps:
  1. Allow the wrapper in $claude_dir/settings.json:
       "permissions": { "allow": ["Bash(oc-delegate:*)"] }
  2. Paste claude-md-snippet.md into $claude_dir/CLAUDE.md so Claude delegates by default.
  3. Smoke test in a throwaway repo (see README).
EOF
