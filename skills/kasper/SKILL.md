---
name: kasper
description: "kasper status | find | graph | rebuild | reinit | mode | style | setup | sync | help. Repo graph + terse-agent rules. Trigger: $kasper, /kasper, /prompts:kasper."
---

Run (from the repo being worked on), substituting the user's arguments:

`python "<this skill's dir>/../../scripts/graph.py" cmd <args> agent=codex`

(`agent=codex` only matters for `setup`; omit for other subcommands.) This also installs `~/.codex/kasper/graph.py` and the `/prompts:kasper` slash command, and keeps the graph fresh.

Reply with the output verbatim, nothing else. If it has a `Comms:` line, follow it from now on. If the output asks you to run setup questions, ask them in one grouped message, then run the given command.

If no kasper rules were injected at session start, run `... cmd sync codex` once: it writes the rules into AGENTS.md.
