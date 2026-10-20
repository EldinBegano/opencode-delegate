#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: bench/make-repo.sh TASK DEST" >&2
  exit 2
fi
task="$1" dest="$2"
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p -- "$dest"
cp -r -- "$here/fixture/." "$dest/"
cd -- "$dest"
if [[ "$task" == bug ]]; then
  sed -i 's/if len(self._data) > self.capacity:/if len(self._data) >= self.capacity:/' src/textkit/cache.py
fi
printf '__pycache__/\n.pytest_cache/\n' > .gitignore
git init -q
git -c user.name=bench -c user.email=bench@example.com -c commit.gpgsign=false add -A
git -c user.name=bench -c user.email=bench@example.com -c commit.gpgsign=false commit -qm "textkit fixture"
