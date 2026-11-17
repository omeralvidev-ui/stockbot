# Usage rules (Minecraft modding)
- Read only the class/lines needed; grep first. Never open `run/`, `build/`, `.gradle/`, `*.jar`, world saves, or decompiled sources.
- Gradle: `./gradlew --offline <task> 2>&1 | tail -n 40`. Build one loader/module, not all.
- Edit in place; never re-emit whole files. No recaps. Answer in <=5 lines unless code is requested.
- Registry/mixin/lang/json boilerplate: batch all files in one pass.
- Record decisions in NOTES.md; `/clear` between features.
