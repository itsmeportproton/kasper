<div align="center">

# Kasper

**shut up and code**

A [Claude Code](https://claude.com/claude-code) plugin that makes the agent terse, keeps it from re-grepping your repo every turn, and lets it finish the whole job instead of stopping at function 50.

![version](https://img.shields.io/badge/version-0.13.0-7cf5c8?style=flat-square)
![languages](https://img.shields.io/badge/languages-any-7cf5c8?style=flat-square)
![deps](https://img.shields.io/badge/dependencies-0-7cf5c8?style=flat-square)

</div>

---

## Why

Same task, two sessions:

```diff
- Now I will inspect the project structure to understand the codebase.
- Let me grep for the function you mentioned...
- I found several files. Next I will read each of them...
- Moving on to phase two. I completed 50 of 200 functions, should I continue?
+ ok cool im on it
+ done: 200 handlers migrated, tests green
```

## What it does

| | |
|---|---|
| **Terse** | No tool narration, no recaps, final reply is one short line. |
| **Asks when it matters** | Ambiguous requirement? It opens a pick-one / pick-many question (`AskUserQuestion`) instead of guessing. Obvious stuff it figures out itself. |
| **Graph first** | Builds a map of the repo (file, symbols, imports). The agent looks there before grepping. |
| **Marathon** | Big plan or 200 similar functions: runs through, no "continue?". |
| **Direct edits** | No `patch.py` / temp scripts that paste code into files. |
| **Language agnostic** | Python, JS/TS, Lua, C/C++, Rust, Go, Java, C#, ... and for anything unknown it still maps the file tree. |
| **Usage bar** | Optional statusline under the input: `5h ███████░░░░░ 62% · 7d ██░░░░░░░░░░ 18% · ctx 34%`. |
| **One-time setup** | First session asks mode, git, subagent cap and autocompact once; the answers apply to every later project. |
| **Cheap** | About 1.2k chars of rules and at most 8k chars of graph per session. |

## Install

```
/plugin marketplace add itsmeportproton/kasper
/plugin install kasper@kasper
```

Restart the session. Kasper turns itself on at every session start, no command needed.

Update: `claude plugin marketplace update kasper`, then `claude plugin uninstall kasper@kasper` and `claude plugin install kasper@kasper`, and restart.

## Setup

The first session in a project (with no saved setup) the agent asks four questions in one `AskUserQuestion`:

| question | options | effect |
|---|---|---|
| comms mode | quiet / normal / chatty / mute (0-3) | `.kasper/config.json` |
| git | commit after each task + push / init + commit only / off | runs `git init` if needed; with `auto` the rules tell the agent to `commit -q` after each task and `push -q` if an origin exists |
| max concurrent subagents | 2 / 1 / custom | `env.CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (restart to apply) |
| autocompact window | 350k / 200k / off | `autoCompactWindow` |

Plus the usage-bar statusline (below). Project settings go to `.claude/settings.local.json`, merged into whatever is there. The answers are also saved to `~/.claude/kasper/defaults.json` and applied silently to every new project. Re-run with `/kasper setup`, or apply directly: `/kasper setup mode=quiet git=auto subagents=2 compact=350000 statusline=on`.

If `gh` is not logged in, Kasper says so; run `! gh auth login` yourself, it is interactive.

### Statusline

A plugin cannot ship a statusline, so `setup` copies `scripts/statusline.py` to `~/.claude/kasper/statusline.py` and points `statusLine` at it in the project's `.claude/settings.local.json`. An existing `statusLine` (project or user) is never replaced. It reads the 5-hour and weekly `rate_limits` plus context usage that Claude Code passes on stdin; segments that are missing (non-subscription accounts) are omitted.

### Other CLIs

Codex CLI, Gemini CLI, Qwen Code, Copilot CLI, Cursor CLI, Aider, OpenCode and Amp have no Claude Code plugin hooks, so Kasper writes its rules into the file each of them reads. Run in your repo:

```
python path/to/kasper/scripts/graph.py cmd sync            # detects installed CLIs
python path/to/kasper/scripts/graph.py cmd sync codex gemini
python path/to/kasper/scripts/graph.py cmd sync all
```

| CLI | file |
|---|---|
| Codex, OpenCode, Amp | `AGENTS.md` |
| Gemini CLI | `GEMINI.md` |
| Qwen Code | `QWEN.md` |
| Copilot CLI | `.github/copilot-instructions.md` |
| Cursor | `.cursor/rules/kasper.mdc` |
| Aider | `CONVENTIONS.md` (start with `--read CONVENTIONS.md`) |

- Kasper only owns the `<!-- kasper:start -->` ... `<!-- kasper:end -->` block. Your own text in those files is never touched, and `unsync` removes the block.
- The block holds the compact rules and points to `.kasper/graph.md`. The graph itself is not pasted in, so these files stay small and don't churn in git.
- `sync` copies the script to `.kasper/kasper.py`, so the agent can run `python .kasper/kasper.py cmd find <name>` and `python .kasper/kasper.py quiet` (refresh) itself.
- Changing `mode` or `style` re-writes the synced blocks. There is no automatic graph refresh in these CLIs, the rules tell the agent to refresh after big changes.
- Tested: the files get written, updated and cleaned up. How each CLI follows them is up to the CLI.

## Examples

**Clear task**

```
you:    make me a parser for this format
kasper: ok cool im on it
        ...works silently...
kasper: done: parser + tests added
```

**Unclear task**

```
you:    make auth work with external providers
kasper: ok, few questions

        Which protocol?                         (pick one)
        > OIDC / OAuth (Recommended)
          SAML
          Custom tokens

        Keep the existing local login?          (pick one)
        > Yes
          No, replace it

        Where do tokens live?                   (pick many)
        [x] Cookies   [ ] Authorization header   [ ] Both
```

**ETA**

```
you:    how long will it take?
kasper: i dont have eta
```

**Code**

Not like this:

```python
def check_urls(urls):
    """
    Iterates over the provided list of URLs and checks...

    Args:
        urls (list[str]): ...
    """
    # Create an empty list that will store all URLs
    available_urls = []
    # Iterate through every URL
    for url in urls:
        ...
```

Like this:

```python
for url in urls:
    try:
        r = requests.get(url, timeout=5)

        # works
        if r.status_code == 200:
            print(url)

        # TODO: redirects, do we count them?

    except requests.RequestException:
        # HACK: dont need the exception, need the list of live urls
        pass
```

Comments say why, not what.

## Commands

```
/kasper                  status panel
/kasper status           version, mode, graph size/age, init state
/kasper find <query>     ranked hits from the graph (path | symbols | used-by)
/kasper graph            open the html repo map
/kasper rebuild          force a graph rebuild
/kasper reinit           re-detect the repo, rebuild everything
/kasper mode [m]         chatty | normal | quiet | mute   (or 0-3)
/kasper style [on|off]   code/docs/commit style rules (default off)
/kasper setup [k=v ...]  first-run wizard; or apply mode git subagents compact statusline
/kasper agentfiles keep|replace
/kasper sync [names|all]  write the rules into other CLIs (see below)
/kasper unsync           remove them
/kasper help
```

```
> /kasper
kasper 0.13.0
mode: normal, style: off
root: D:\projects\my-game
graph: ready, 418 files, 3m old, inject 7.9k/8k chars
commands: status | find | graph | rebuild | mode | style | agentfiles | reinit | help
```

## Modes

| mode | what it does |
|---|---|
| `chatty` | useful commentary allowed, never routine tool narration |
| `normal` | ack, questions, real blockers, otherwise silent. **default** |
| `quiet` | questions, blockers and the final line only |
| `mute` | silent unless it cannot continue without an answer |

The mode is saved per repository in `.kasper/config.json` (the default for new repos comes from `/kasper setup`). Only the active mode's one-line rule goes into the context.

## The graph

On session start Kasper scans the repo once and writes:

```
.kasper/graph.md     path | symbol:line | imports      (what the agent reads)
.kasper/graph.html   standalone page, no dependencies  (what you read)
.kasper/index.json   per-file cache (mtime + size), only changed files are rescanned
```

```
src/core/AI.cpp | AIManagerUpdate:12 SensesUpdate:35 AIAudioUpdate:50 | core/patcher.h core/List.h
src/render/gl.cpp | InitGL:8 DrawFrame:41 | core/patcher.h
```

- Respects `.gitignore` (uses `git ls-files`, falls back to a directory walk).
- After an edit only that file's entry is updated (the hook gets the path from Claude Code), no repo-wide rescan.
- Skips huge, generated and minified files (over 1 MB, 20k lines, or very long lines): they stay in the tree, without symbols.
- Symbols and imports are extracted for the common languages. For everything else you still get the file tree.
- If the graph is over 8k chars, the injected part is the most-imported files plus a per-directory summary; the full file stays on disk.
- On big repos the agent queries instead of reading everything: `/kasper find auth` returns up to 15 ranked hits (name and symbol match, boosted by how many files import it).
- The graph is an index. The agent verifies in the source.

Open `/kasper graph` for a small repo map: collapsible tree, search by path, symbol or language (`/` focuses, `Esc` clears), language filters, and a side panel that lists what a file depends on and what imports it. About 6 KB of vanilla HTML/JS, dark and light themes.

## Files and style

Kasper's core rules cover communication, navigation and execution only. The rest is opt-in:

- `/kasper style on` adds: comments only for intent/constraints, no summary `.md`, real docs go to `README.md` (short, with links) + `docs/*.md` (committed), no diff/commit text in replies.
- Agent files `CLAUDE.md`, `AGENTS.md`, `TODO.md`, `PROJECT.md`: if none exist, Kasper creates empty ones and adds them to `.gitignore`. If some already exist, it never touches them; the agent asks you (`AskUserQuestion`) whether Kasper should manage them (gitignore only, content untouched) or leave them alone. The answer is saved by `/kasper agentfiles keep|replace`.

## Layout

```
.claude-plugin/   plugin.json, marketplace.json
hooks/hooks.json  SessionStart -> init + inject, PostToolUse(Edit|Write) -> refresh graph
commands/kasper.md
scripts/graph.py  graph, commands, setup; python 3.8+ stdlib only
scripts/statusline.py  usage-bar statusline (installed by setup)
```

## Not included

No daemon, database, embeddings, remote calls or dependencies. The tool that saves tokens shouldn't cost more than it saves.

---

<div align="center">shut up and code</div>
