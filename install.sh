#!/usr/bin/env bash
# Plug claude-usage-saver into your Claude Code: global skill + deny-list.
# Usage: ./install.sh [minecraft|roblox|webapp]   (optional: also drops CLAUDE.md in the current project)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="$HOME/.claude"
mkdir -p "$dest/skills"
rm -rf "$dest/skills/usage-saver"
cp -r "$here/skills/usage-saver" "$dest/skills/usage-saver"
mkdir -p "$dest/skills/usage-saver/scripts" && cp "$here/scripts/budget.py" "$dest/skills/usage-saver/scripts/"
echo "skill installed -> $dest/skills/usage-saver"
if [ ! -f "$dest/settings.json" ]; then
  cp "$here/templates/settings.deny.json" "$dest/settings.json"
  echo "settings.json created with deny-list"
else
  echo "NOTE: $dest/settings.json exists; merge templates/settings.deny.json into it manually."
fi
if [ "${1:-}" ]; then
  cp "$here/templates/CLAUDE.$1.md" ./CLAUDE.md && echo "CLAUDE.md ($1) written to $(pwd)"
fi
