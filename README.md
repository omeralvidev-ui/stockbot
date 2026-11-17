# claude-usage-saver

Stop running out of Claude. Drop-in rules, templates and a calculator for **Minecraft modding, Roblox, apps and websites**.

## Install (plug into Claude Code)
```bash
git clone https://github.com/omeralvidev-ui/stockbot claude-usage-saver   # or wherever you push this
cd claude-usage-saver
./install.sh roblox        # or: minecraft | webapp  (writes CLAUDE.md into current project)
```
Or as a plugin: `/plugin marketplace add <this repo>` then `/plugin install claude-usage-saver`.

## The math
Every turn re-reads the whole context. With baseline `C0`, growth `g` per turn, `n` turns:

    tokens(n) = n·C0 + g·n(n+1)/2          → quadratic

With prompt caching (read r=0.1, write w=1.25):

    cost(n) = r·(n·C0 + g·n(n−1)/2) + w·(C0 + g·n)

Resetting costs `R` tokens to rebuild context. Average cost per turn over a segment of `m` turns:

    A(m) = w·R/m + r·(C0 + g·(m+1)/2)
    A'(m) = 0  ⇒  m* = √(2·w·R / (r·g))

Example `R=15000, g=3000` ⇒ `m* ≈ 11` turns. Two levers: **shrink g** (narrow reads, edits not rewrites, short answers) and **reset near m\***.

```bash
python scripts/budget.py --n 40 --c0 8000 --g 3000 --R 15000 --limit 2000000
```

## What's inside
| Path | Purpose |
|---|---|
| `skills/usage-saver/` | Skill with the rules Claude follows |
| `templates/CLAUDE.{minecraft,roblox,webapp}.md` | Per-stack project rules |
| `templates/settings.deny.json` | Blocks reading `node_modules`, builds, `.rbxl`, jars, lockfiles |
| `scripts/budget.py` | Session cost + optimal-reset calculator |

## Top habits
1. `/clear` between tasks; `/compact` around turn 10–15.
2. Keep `NOTES.md` so resets lose nothing.
3. Cheaper model for UI/boilerplate, Opus only for hard problems.
4. Narrow test/build commands, `| tail -n 40`.
