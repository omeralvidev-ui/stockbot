---
name: usage-saver
description: Keep Claude usage low while building Minecraft mods, Roblox games, mobile apps and websites. Use at the start of a dev session, when the context is getting long, when a task is large, or when the user mentions usage limits, running out of tokens, or "save usage".
---

# Usage Saver

Context is re-read every turn, so cost grows **quadratically** with session length:
`tokens ≈ n·C0 + g·n(n+1)/2` (n turns, C0 baseline context, g growth per turn).
Cutting g and resetting at the right time is what saves usage.

## Rules (follow silently, don't narrate them)

1. **Read narrowly.** Grep for the symbol, then read only the needed line range. Never read whole large files, lockfiles, build output, or generated code.
2. **Never read/scan:** `node_modules`, `build`, `dist`, `.gradle`, `run`, `out`, `Packages`, `*.lock`, `*.min.js`, `*.rbxl`, `*.rbxlx`, `*.jar`, `*.class`, images, models, world saves.
3. **Edit, don't rewrite.** Use targeted edits; never re-emit an unchanged file.
4. **Short outputs.** Answer in the fewest words that are correct. No restating the task, no recap after edits, no unrequested alternatives.
5. **Batch.** Run independent tool calls in parallel; plan edits across files before making them.
6. **Right-size the model.** Haiku/Sonnet for boilerplate, UI, config, renames, tests. Opus only for architecture, hard bugs, security.
7. **Delegate noisy work.** Big searches/log reads go to a subagent so only the conclusion enters context.
8. **Tests/builds:** run the narrowest command (single test, single module), pipe through `tail -n 40`.
9. **Ask once, up front** if the task is ambiguous; don't iterate on guesses.

## When to reset
Optimal reset interval `m* = sqrt(2·w·R / (ρ·g))`, ρ = p·w + (1−p)·r (w=1.25 write, r=0.1 read, p = share of turns after a cache expiry, R rebuild cost, g growth).
Typical R=15k, g=3k, p=0.1 ⇒ m* ≈ 8 turns; long pauses expire the cache, so finish or `/clear` before breaks. In practice: **`/clear` between unrelated tasks, `/compact` around turn ~8–15 of a single task**, and keep a short `NOTES.md` of decisions so a reset loses nothing.

Run `python scripts/budget.py --n 40 --p 0.1 --limit 2000000` (in the plugin dir) to compute numbers for the current session.

## Stack notes
- **Minecraft (Fabric/Forge/NeoForge):** don't read decompiled/mapped sources or `run/`; check one class via grep. Keep Gradle output to `tail`. Use `--offline` and `--daemon`.
- **Roblox (Luau/Rojo):** work from `src/` Luau files only; never open `.rbxl`. Keep systems as small ModuleScripts so edits touch few lines.
- **Web/App:** read `package.json` scripts once, run single-file lint/typecheck, never dump `npm ls` or lockfiles.

See `templates/` for drop-in CLAUDE.md and settings.
