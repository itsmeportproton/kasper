<div align="center">

# Kasper

**shut up and code**

A [Claude Code](https://claude.com/claude-code) plugin that makes the agent terse, keeps it from re-grepping your repo every turn, and lets it finish the whole job instead of stopping at function 50.

![version](https://img.shields.io/badge/version-0.11.0-7cf5c8?style=flat-square)
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
| **Cheap** | About 1.2k chars of rules and at most 8k chars of graph per session. |

## Install

```
/plugin marketplace add itsmeportproton/kasper
/plugin install kasper@kasper
```

Restart the session. Kasper turns itself on at every session start, no command needed.

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
/kasper agentfiles keep|replace
/kasper help
```

```
> /kasper
kasper 0.11.0
mode: normal
root: D:\projects\my-game
graph: ready, 418 files, 3m old, inject 7.9k/8k chars
commands: status | graph | rebuild | mode | reinit | help
```

## Modes

| mode | what it does |
|---|---|
| `chatty` | useful commentary allowed, never routine tool narration |
| `normal` | ack, questions, real blockers, otherwise silent. **default** |
| `quiet` | questions, blockers and the final line only |
| `mute` | silent unless it cannot continue without an answer |

The mode is saved per repository in `.kasper/config.json`. Only the active mode's one-line rule goes into the context.

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
scripts/graph.py  the whole thing, python 3.8+ stdlib only
```

## Not included

No daemon, database, embeddings, remote calls or dependencies. The tool that saves tokens shouldn't cost more than it saves.

---

<div align="center">shut up and code</div>
