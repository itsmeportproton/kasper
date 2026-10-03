import json
import sys
from pathlib import Path

HOME = Path.home()


def bar(p, n=12):
    k = round(max(0, min(100, p)) / 100 * n)
    return "█" * k + "░" * (n - k)


def jl(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def k(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(int(n))


def agents(tp):
    """Agent/Task tool_use calls in the transcript tail that have no tool_result yet."""
    try:
        with open(tp, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400_000))
            lines = f.read().decode("utf-8", "ignore").splitlines()[1:]
    except Exception:
        return None
    pend = set()
    for ln in lines:
        try:
            c = json.loads(ln).get("message", {}).get("content")
        except Exception:
            continue
        for b in c if isinstance(c, list) else ():
            if b.get("type") == "tool_use" and b.get("name") in ("Agent", "Task"):
                pend.add(b.get("id"))
            elif b.get("type") == "tool_result":
                pend.discard(b.get("tool_use_id"))
    return len(pend)


d = json.load(sys.stdin) if not sys.stdin.isatty() else {}
sys.stdout.reconfigure(encoding="utf-8")
try:
    kd = HOME / ".claude" / "kasper"
    kd.mkdir(parents=True, exist_ok=True)
    (kd / "last.json").write_text(json.dumps(d), encoding="utf-8")  # read by /kasper context
except Exception:
    pass

head = []
if (d.get("model") or {}).get("display_name"):
    head.append(d["model"]["display_name"])
for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
    p = (d.get("rate_limits") or {}).get(key, {}).get("used_percentage")
    if p is not None:
        head.append(f"{label} {bar(p)} {p:.0f}%")
cw = d.get("context_window") or {}
size = cw.get("context_window_size")
pct = cw.get("used_percentage")
used = cw.get("total_input_tokens")
if used is None and size and pct is not None:
    used = size * pct / 100
if pct is not None:
    head.append(f"ctx {pct:.0f}%" + (f" ({k(used)}/{k(size)})" if size and used is not None else ""))
print(" · ".join(head))

cwd = Path((d.get("workspace") or {}).get("current_dir") or d.get("cwd") or ".")
root = next((p for p in [cwd, *cwd.parents] if (p / ".kasper" / "config.json").exists()), None)
cfg = jl(root / ".kasper" / "config.json") if root else {}
st = {**jl(HOME / ".claude" / "settings.json"), **(jl(root / ".claude" / "settings.local.json") if root else {})}

s = ["kasper stats", f"mode {cfg.get('mode', '?')}"]
n = agents(d.get("transcript_path"))
mx = (st.get("env") or {}).get("CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS", "?")
if n is not None:
    s.append(f"agents {n}/{mx}")
if used is not None:
    s.append(f"{k(used)} used")
    lim = st.get("autoCompactWindow") or (size * 0.95 if size else None)
    if lim:
        s.append(f"{k(max(0, lim - used))} to compact")
acc = jl(HOME / ".claude.json").get("oauthAccount") or {}
who = acc.get("displayName") or (acc.get("emailAddress") or "").split("@")[0]
if who:
    s.append(who)
print(" · ".join(s[:1]) + ": " + " · ".join(s[1:]))

base = root or cwd
made = cfg.get("created", [])
have = [n for n in ("CLAUDE.md", "AGENTS.md") if (base / n).exists()]
print("kasper init: " + ("no init (no CLAUDE.md, no AGENTS.md)" if not have else
                         "init (by kasper)" if all(n in made for n in have) else "init (not by kasper)"))
