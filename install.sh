#!/usr/bin/env bash
# Plug claude-usage-saver into Claude Code: global skill + merged deny/ask list.
# Usage: ./install.sh [minecraft|roblox|webapp]  (also writes CLAUDE.md into the current project)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="$HOME/.claude"
mkdir -p "$dest/skills"
rm -rf "$dest/skills/usage-saver"
cp -r "$here/skills/usage-saver" "$dest/skills/usage-saver"
mkdir -p "$dest/skills/usage-saver/scripts" && cp "$here/scripts/budget.py" "$dest/skills/usage-saver/scripts/"
echo "skill -> $dest/skills/usage-saver"

python3 - "$dest/settings.json" "$here/templates/settings.deny.json" <<'PY'
import json, os, shutil, sys
target, tmpl = sys.argv[1], sys.argv[2]
new = json.load(open(tmpl))
cur = {}
if os.path.exists(target):
    shutil.copy(target, target + ".bak")
    cur = json.load(open(target))
perm = cur.setdefault("permissions", {})
for k in ("deny", "ask"):
    have = perm.setdefault(k, [])
    perm[k] = have + [r for r in new["permissions"][k] if r not in have]
json.dump(cur, open(target, "w"), indent=2)
print(f"settings merged -> {target} (backup: {target}.bak)" if os.path.exists(target + ".bak") else f"settings created -> {target}")
PY

if [ "${1:-}" ]; then
  [ -f "$here/templates/CLAUDE.$1.md" ] || { echo "unknown stack: $1 (minecraft|roblox|webapp)"; exit 1; }
  if [ -f ./CLAUDE.md ]; then cat "$here/templates/CLAUDE.$1.md" >> ./CLAUDE.md; echo "appended to ./CLAUDE.md"
  else cp "$here/templates/CLAUDE.$1.md" ./CLAUDE.md; echo "wrote ./CLAUDE.md ($1)"; fi
fi
