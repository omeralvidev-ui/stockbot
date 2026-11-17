# Usage rules (Roblox / Luau)
- Work in `src/` (Rojo) only. Never open `.rbxl/.rbxlx`, `Packages/`, `*.lock`.
- Small ModuleScripts; change the minimum lines. Never re-emit unchanged scripts.
- Server-authoritative: validate every RemoteEvent argument server-side.
- Run `selene`/`stylua` on changed files only. No recaps; <=5 lines unless code requested.
- Record decisions in NOTES.md; `/clear` between systems.
