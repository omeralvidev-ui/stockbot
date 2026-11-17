# Usage rules (apps & websites)
- Read `package.json` scripts once. Never open `node_modules/`, `dist/`, `build/`, `.next/`, lockfiles, `*.min.*`, source maps.
- Typecheck/lint/test the changed file or single test only; pipe output through `tail -n 40`.
- Edit components in place; don't rewrite files or restate the task. <=5 lines unless code requested.
- Batch related file edits into one pass. Haiku/Sonnet for UI/CSS/config, Opus only for architecture/hard bugs.
- Record decisions in NOTES.md; `/clear` between features.
