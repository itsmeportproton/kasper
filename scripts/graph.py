import hashlib
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

VERSION = "0.10.3"
CAP = 8000

MODES = {
    "chatty": "concise useful commentary allowed; never narrate routine tool calls.",
    "normal": "brief ack, questions, useful blockers; otherwise work silently.",
    "quiet": "questions/blockers/final only.",
    "mute": "silent execution; ask/speak only when blocked or required, then final.",
}
ALIAS = {"0": "mute", "1": "quiet", "2": "normal", "3": "chatty"}

RULES = """kasper {v}
- Terse. No routine tool narration; speak when useful, blocked, or when a question saves work.
- Materially ambiguous (product/API/arch)? Ask via the AskUserQuestion tool (1-4 questions, 2-4 options each, multiSelect when choices combine, recommended option first), not as chat text. Never guess or mass-read instead. Cheap facts: find them yourself.
- Finish whole tasks; no stopping at arbitrary phase/count, no "continue?" when the next step is clear.
- Navigate graph/search first, read only needed source; reread only if stale/partial. Graph is an index, verify in source.
- Edit directly; no scratch/temp/patch scripts unless the task is the script. Batch independent calls.
- Match repo language/style/tests; minimal scope, no unrelated refactors. Comments only for intent/constraints/addresses.
- No fake ETA ("i dont have eta"). No summary .md files unless asked. CLAUDE.md AGENTS.md TODO.md PROJECT.md are gitignored agent files; real docs go to README.md (short, links) + docs/*.md, committed, after the first skeleton.
- Final reply short: "done: <what>".
Comms: {c}
"""

HELP = """/kasper             status panel
/kasper status      details
/kasper graph       open html map (graph rebuild: force)
/kasper rebuild     force graph rebuild
/kasper reinit      re-detect repo, rebuild all
/kasper mode [m]    chatty|normal|quiet|mute (0-3)
/kasper help"""

LANG = {
    ".py": "py", ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "jsx", ".ts": "ts", ".tsx": "tsx", ".lua": "lua",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp", ".inl": "cpp",
    ".rs": "rust", ".go": "go", ".java": "java", ".kt": "kotlin", ".cs": "cs", ".php": "php", ".rb": "ruby",
    ".zig": "zig", ".sh": "sh", ".bash": "sh", ".ps1": "ps1", ".sql": "sql", ".html": "html", ".css": "css",
    ".scss": "css", ".swift": "swift", ".m": "objc", ".scala": "scala", ".dart": "dart", ".asm": "asm", ".s": "asm",
    ".md": "md", ".json": "json", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".txt": "txt", ".xml": "xml",
    ".cmake": "cmake", ".gradle": "gradle", ".vue": "vue", ".svelte": "svelte",
}
NOSCAN = {".md", ".json", ".yml", ".yaml", ".toml", ".txt", ".xml", ".css", ".scss", ".html"}
CFAMILY = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".inl", ".m"}
BIN = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".obj", ".a", ".lib",
       ".pdf", ".zip", ".7z", ".gz", ".tar", ".mp3", ".wav", ".ogg", ".mp4", ".ttf", ".otf", ".woff", ".woff2", ".pyc", ".lock"}
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".kasper", ".idea", ".vs"}

SYM = re.compile(
    r"^\s*(?:(?:export|default|pub(?:\([\w:]+\))?|public|private|protected|internal|static|async|local|final|abstract|open|override|suspend|unsafe|extern)\s+)*"
    r"(?:def|class|function|func|fun|fn|struct|interface|trait|enum|type|impl|module|namespace|object|record|sub|proc|macro)\s+([A-Za-z_][\w.:]*)")
CFUNC = re.compile(r"^[A-Za-z_][\w\s\*&:<>,~]*?\b([A-Za-z_]\w*)\s*\([^;]*$")
NOTFUNC = {"if", "for", "while", "switch", "return", "else", "sizeof", "defined", "catch"}
IMP = re.compile(
    r"""^\s*(?:from\s+([\w./]+)\s+import"""
    r"""|(?:import|use|using)\s+(?:static\s+)?(?:.*?\bfrom\s+)?['"]?([\w./:@\\-]+)"""
    r"""|\#\s*include\s*["<]([^">]+)"""
    r"""|.*\brequire(?:_once)?\s*\(?\s*['"]([^'"]+))""", re.X)


def find_root(p):
    for d in [p, *p.parents]:
        if (d / ".git").exists():
            return d
    return p


def list_files(root):
    names = None
    if (root / ".git").exists():
        try:
            out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root, capture_output=True, timeout=30).stdout
            names = [f for f in out.decode("utf-8", "ignore").split("\0") if f]
        except Exception:
            names = None
    if names is None:
        names = []
        for d, dirs, fs in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP]
            names += [os.path.relpath(os.path.join(d, f), root).replace("\\", "/") for f in fs]
    return sorted(f for f in set(names) if not SKIP & set(f.split("/")) and Path(f).suffix.lower() not in BIN and (root / f).is_file())


def scan(path, ext):
    if ext not in LANG or ext in NOSCAN:
        return [], []
    syms, imps = [], []
    for n, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
        m = SYM.match(line) or (ext in CFAMILY and not line.startswith("#") and CFUNC.match(line))
        if m and m[1] not in NOTFUNC:
            syms.append(f"{m[1].rstrip(':.')}:{n}")
        elif m := IMP.match(line):
            imps.append((m[1] or m[2] or m[3] or m[4]).rstrip(";"))
    return syms, sorted(set(imps))


def load_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def refresh(root, force=False):
    k = root / ".kasper"
    k.mkdir(exist_ok=True)
    (k / ".gitignore").write_text("*\n")
    cfg = load_json(k / "config.json", {})
    old = {} if force or cfg.get("version") != VERSION else load_json(k / "index.json", {})
    idx = {}
    for f in list_files(root):
        st = (root / f).stat()
        o = old.get(f)
        if o and o[0] == st.st_mtime_ns and o[1] == st.st_size:
            idx[f] = o
        else:
            idx[f] = [st.st_mtime_ns, st.st_size, *scan(root / f, Path(f).suffix.lower())]
    if idx != old or not (k / "graph.md").exists():
        (k / "index.json").write_text(json.dumps(idx), encoding="utf-8")
        (k / "graph.md").write_text(graph_text(idx), encoding="utf-8")
    cfg.update(version=VERSION, root=str(root), files=len(idx))
    cfg.setdefault("mode", "normal")
    (k / "config.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return idx, cfg


def graph_text(idx):
    return "\n".join(f"{f} | {' '.join(v[2][:200])} | {' '.join(v[3])}" if v[2] or v[3] else f for f, v in idx.items())


def inject(idx):
    full = graph_text(idx)
    if len(full) <= CAP:
        return full
    for depth in (3, 2, 1):
        dirs = {}
        for f in idx:
            d = "/".join(f.split("/")[:-1][:depth]) or "."
            dirs.setdefault(d, []).append(Path(f).suffix.lower())
        body = "\n".join(f"{d}/ {len(e)}" for d, e in sorted(dirs.items()))
        if len(body) <= CAP - 80:
            break
    return f"graph: {len(idx)} files; truncated; full: .kasper/graph.md\n" + body[:CAP - 80]


def init_docs(root):
    agent = ["CLAUDE.md", "AGENTS.md", "TODO.md", "PROJECT.md"]
    for name in agent:
        (root / name).touch()
    gi = root / ".gitignore"
    have = gi.read_text().splitlines() if gi.exists() else []
    new = [p for p in agent + [".kasper/"] if p not in have]
    if new:
        gi.write_text("\n".join(have + new) + "\n")


def resolve(idx):
    stems = {}
    for f in idx:
        stems.setdefault(Path(f).stem.lower(), []).append(f)
    deps = {}
    for f, v in idx.items():
        out = set()
        for i in v[3]:
            s = i[:-len(Path(i).suffix)] if Path(i).suffix.lower() in LANG else i
            s = s.replace("::", "/").replace("\\", "/")
            if "/" not in s:
                s = s.replace(".", "/")
            s = s.lstrip("./")
            c = stems.get(s.split("/")[-1].lower(), [])
            hit = [x for x in c if os.path.splitext(x)[0].lower().endswith(s.lower())] or (c if len(c) == 1 else [])
            out.update(x for x in hit if x != f)
        deps[f] = sorted(out)
    return deps


def build_html(root, idx):
    deps = resolve(idx)
    data = {"root": root.name, "files": [[f, LANG.get(Path(f).suffix.lower(), Path(f).suffix.lstrip(".") or "-"), v[2], v[3], deps[f]] for f, v in idx.items()]}
    blob = json.dumps(data).replace("<", "\\u003c")
    out = root / ".kasper" / "graph.html"
    out.write_text(HTML.replace("__DATA__", blob), encoding="utf-8")
    return out


def status(root, idx, cfg):
    g = root / ".kasper" / "graph.md"
    age = int(time.time() - g.stat().st_mtime) if g.exists() else -1
    ago = "?" if age < 0 else f"{age}s" if age < 120 else f"{age // 60}m" if age < 7200 else f"{age // 3600}h"
    mode = cfg["mode"]
    return (f"kasper {VERSION}\nmode: {mode}\nroot: {root}\n"
            f"graph: ready, {len(idx)} files, {ago} old, inject {len(inject(idx))}/{CAP} chars (full {g.stat().st_size if g.exists() else 0})\n"
            f"init: {'ok' if g.exists() and cfg.get('version') == VERSION else 'broken, run /kasper reinit'}")


def cmd(root, args):
    a = args[0] if args else ""
    rest = args[1:]
    if a == "mode":
        idx, cfg = refresh(root)
        m = ALIAS.get(rest[0], rest[0]) if rest else ""
        if m in MODES:
            cfg["mode"] = m
            (root / ".kasper" / "config.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
            return f"mode: {m}\nComms: {MODES[m]}"
        return f"mode: {cfg['mode']}\n" + " | ".join(MODES) + "\n/kasper mode <name|0-3>"
    if a in ("rebuild", "reinit") or rest[:1] == ["rebuild"]:
        if a == "reinit" and (root / ".git").exists():
            init_docs(root)
        idx, cfg = refresh(root, force=True)
        if a == "reinit":
            build_html(root, idx)
        return f"{a}: {len(idx)} files"
    if a == "graph":
        idx, cfg = refresh(root)
        out = build_html(root, idx)
        try:
            webbrowser.open(out.as_uri())
        except Exception:
            pass
        return f"graph: {out}"
    idx, cfg = refresh(root)
    if a == "help":
        return HELP
    if a == "status":
        return status(root, idx, cfg)
    return status(root, idx, cfg).split("\ninit:")[0] + "\ncommands: status | graph | rebuild | mode | reinit | help"


def session(root):
    if (root / ".git").exists():
        init_docs(root)
    idx, cfg = refresh(root)
    print(RULES.format(v=VERSION, c=MODES[cfg["mode"]]) + "graph (path | symbol:line | imports):\n" + inject(idx))


HTML = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>kasper graph</title>
<style>
:root{--bg:#0b0d12;--p:#12151d;--l:#1f2430;--t:#d7dbe6;--m:#7c8497;--a:#7cf5c8}
@media(prefers-color-scheme:light){:root{--bg:#f5f6f9;--p:#fff;--l:#dfe2ea;--t:#1c2030;--m:#6b7285;--a:#0a8f68}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:13px/1.4 ui-monospace,Consolas,monospace;height:100vh;display:flex;flex-direction:column}
header{padding:10px 14px;border-bottom:1px solid var(--l);display:flex;gap:10px;align-items:center;flex-wrap:wrap}
h1{font-size:14px;margin:0;color:var(--a)}#q{flex:1;min-width:160px;background:var(--p);border:1px solid var(--l);color:var(--t);padding:6px 10px;border-radius:6px;font:inherit}
#q:focus{outline:none;border-color:var(--a)}#st{color:var(--m)}#langs{display:flex;gap:4px;flex-wrap:wrap;width:100%}
main{flex:1;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);min-height:0}
@media(max-width:700px){main{grid-template-columns:1fr;grid-template-rows:1fr 1fr}}
#tree,#det{overflow:auto;padding:6px 0}#det{border-left:1px solid var(--l);padding:12px 14px;background:var(--p)}
.r{padding:2px 8px;cursor:pointer;display:flex;gap:8px;align-items:center;white-space:nowrap;transition:background .12s}.r:hover{background:var(--l)}
.dir{color:var(--m)}.c{margin-left:auto;font-size:11px}.n{overflow:hidden;text-overflow:ellipsis}
.sel{background:var(--l);box-shadow:inset 3px 0 var(--a),0 0 12px color-mix(in srgb,var(--a) 25%,transparent)}.rel{box-shadow:inset 3px 0 #f5c26b}
.b{font-size:10px;padding:0 6px;border-radius:8px;cursor:pointer;color:hsl(var(--h) 80% 70%);background:hsl(var(--h) 50% 20%/.45);border:1px solid hsl(var(--h) 50% 40%/.5)}
@media(prefers-color-scheme:light){.b{color:hsl(var(--h) 70% 30%);background:hsl(var(--h) 70% 90%)}}
h2{font-size:13px;margin:0 8px 6px 0;display:inline;word-break:break-all}h3{font-size:11px;color:var(--m);margin:14px 0 4px;text-transform:uppercase;letter-spacing:.06em}
.chips{display:flex;flex-wrap:wrap;gap:4px}.chip{padding:1px 7px;border:1px solid var(--l);border-radius:5px;font-size:12px}.lk{cursor:pointer;color:var(--a)}.lk:hover{border-color:var(--a)}.m{padding:6px 14px;color:var(--m)}
</style>
<header><h1 id=h>kasper</h1><input id=q placeholder="search path / symbol / lang   ( / )" autocomplete=off><span id=st></span><div id=langs></div></header>
<main><div id=tree></div><div id=det><span class=m>pick a file</span></div></main>
<script id=d type=application/json>__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('d').textContent),F=D.files,by={},$=s=>document.querySelector(s);
F.forEach((f,i)=>by[f[0]]=i);
const rev=F.map(()=>[]);F.forEach((f,i)=>f[4].forEach(p=>{if(p in by)rev[by[p]].push(f[0])}));
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e};
const hue=s=>{let h=0;for(const c of s)h=(h*31+c.charCodeAt(0))%360;return h};
const badge=l=>{const b=el('span','b',l);b.style.setProperty('--h',hue(l));return b};
const T={n:'',p:'',d:{},f:[],c:0};
F.forEach((f,i)=>{let n=T,p='';const ps=f[0].split('/');ps.pop();n.c++;for(const s of ps){p+=s+'/';n=n.d[s]??={n:s,p,d:{},f:[],c:0};n.c++}n.f.push(i)});
const open=new Set(['']);let sel=-1,q='',lang='';
function reveal(path){let p='';path.split('/').slice(0,-1).forEach(s=>{p+=s+'/';open.add(p)});q='';$('#q').value=''}
function row(i,d,rel){const f=F[i],r=el('div','r'+(i==sel?' sel':'')+(rel.has(f[0])?' rel':''));r.style.paddingLeft=(d*14+8)+'px';
 r.append(el('span','n',q?f[0]:f[0].split('/').pop()),badge(f[1]));r.onclick=()=>{sel=i;render();detail()};return r}
function render(){
 const box=$('#tree');box.textContent='';const rel=new Set();
 if(sel>=0){F[sel][4].forEach(p=>rel.add(p));rev[sel].forEach(p=>rel.add(p))}
 if(q||lang){const m=[];for(let i=0;i<F.length&&m.length<300;i++){const f=F[i];
  if(lang&&f[1]!==lang)continue;
  if(q&&!(f[0].toLowerCase().includes(q)||f[1]==q||f[2].some(s=>s.toLowerCase().includes(q))))continue;m.push(i)}
  m.forEach(i=>box.append(row(i,0,rel)));if(m.length==300)box.append(el('div','m','first 300 matches'));return}
 const walk=(n,d)=>{Object.values(n.d).sort((a,b)=>a.n<b.n?-1:1).forEach(c=>{
  const r=el('div','r dir',(open.has(c.p)?'▾ ':'▸ ')+c.n+'/');r.style.paddingLeft=(d*14+8)+'px';r.append(el('span','c',c.c));
  r.onclick=()=>{open.has(c.p)?open.delete(c.p):open.add(c.p);render()};box.append(r);if(open.has(c.p))walk(c,d+1)});
  n.f.slice(0,400).forEach(i=>box.append(row(i,d,rel)));if(n.f.length>400)box.append(el('div','m','+'+(n.f.length-400)+' more, use search'))};
 walk(T,0)}
function detail(){
 const p=$('#det');p.textContent='';if(sel<0)return;const f=F[sel];p.append(el('h2',0,f[0]),badge(f[1]));
 const sec=(t,items,link)=>{if(!items.length)return;p.append(el('h3',0,t+' '+items.length));const w=el('div','chips');
  items.forEach(x=>{const k=link&&x in by,c=el('span','chip'+(k?' lk':''),x);if(k)c.onclick=()=>{sel=by[x];reveal(x);render();detail()};w.append(c)});p.append(w)};
 sec('symbols',f[2]);sec('depends on',f[4],1);sec('imported by',rev[sel],1);sec('imports',f[3])}
const cnt={};F.forEach(f=>cnt[f[1]]=(cnt[f[1]]||0)+1);
$('#h').textContent='kasper · '+D.root;
$('#st').textContent=F.length+' files · '+Object.keys(T.d).length+' top dirs';
Object.entries(cnt).sort((a,b)=>b[1]-a[1]).slice(0,14).forEach(([l,n])=>{const b=badge(l+' '+n);b.onclick=()=>{lang=lang==l?'':l;render()};$('#langs').append(b)});
$('#q').oninput=e=>{q=e.target.value.toLowerCase().trim();render()};
addEventListener('keydown',e=>{if(e.key=='/'&&document.activeElement!=$('#q')){e.preventDefault();$('#q').focus()}else if(e.key=='Escape'){q=lang='';$('#q').value='';render()}});
render();
</script>"""

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    root = find_root(Path.cwd())
    mode = sys.argv[1] if len(sys.argv) > 1 else "session"
    if mode == "cmd":
        print(cmd(root, sys.argv[2:]))
    elif mode == "quiet":
        refresh(root)
    else:
        session(root)
