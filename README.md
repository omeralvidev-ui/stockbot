# claude-usage-saver

Stop running out of Claude. Drop-in rules, templates and a calculator for **Minecraft modding, Roblox, apps and websites**.

## Install (plug into Claude Code)
```bash
git clone https://github.com/<you>/claude-usage-saver
cd claude-usage-saver
./install.sh roblox        # or: minecraft | webapp  (writes CLAUDE.md into current project)
```
`install.sh` merges the deny/ask rules into your existing `~/.claude/settings.json` (backup kept as `.bak`) and appends to an existing project `CLAUDE.md`.

Or as a plugin: `/plugin marketplace add <you>/claude-usage-saver`, then `/plugin install claude-usage-saver@claude-usage-saver`.

## The math
Every turn re-reads the whole context. With baseline `C0`, growth `g` per turn, `n` turns:

    tokens(n) = n·C0 + g·n(n+1)/2          → quadratic

With prompt caching (read r=0.1, write w=1.25) and a fraction `p` of turns that follow a cache expiry (pauses), the effective rate is ρ = p·w + (1−p)·r:

    cost(n) = ρ·(n·C0 + g·n(n−1)/2) + w·(C0 + g·n)

Resetting costs `R` tokens to rebuild context. Average cost per turn over a segment of `m` turns:

    A(m) = w·R/m + ρ·(C0 + g·(m+1)/2)
    A'(m) = 0  ⇒  m* = √(2·w·R / (ρ·g))

Example `R=15000, g=3000, p=0.1` ⇒ `m* ≈ 8` turns; more pauses (bigger p) ⇒ reset sooner. The numbers are a model with assumed inputs, not a guarantee: measure your own C0/g with `/context`. Formulas are checked against brute force in `tests/`. Two levers: **shrink g** (narrow reads, edits not rewrites, short answers) and **reset near m\***.

```bash
python scripts/budget.py --n 40 --c0 8000 --g 3000 --R 15000 --p 0.1 --limit 2000000
```

## What's inside
| Path | Purpose |
|---|---|
| `skills/usage-saver/` | Skill with the rules Claude follows |
| `templates/CLAUDE.{minecraft,roblox,webapp}.md` | Per-stack project rules |
| `templates/settings.deny.json` | Denies `node_modules`, builds, `.rbxl`, jars; *asks* before lockfiles |
| `scripts/budget.py` | Session cost + optimal-reset calculator |

## Top habits
1. `/clear` between tasks; `/compact` around turn 8–15.
2. Keep `NOTES.md` so resets lose nothing.
3. Cheaper model for UI/boilerplate, Opus only for hard problems.
4. Narrow test/build commands, `| tail -n 40`.
