import json
import sys


def bar(p, n=12):
    k = round(max(0, min(100, p)) / 100 * n)
    return "█" * k + "░" * (n - k)


d = json.load(sys.stdin) if not sys.stdin.isatty() else {}
sys.stdout.reconfigure(encoding="utf-8")
out = []
for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
    p = (d.get("rate_limits") or {}).get(key, {}).get("used_percentage")
    if p is not None:
        out.append(f"{label} {bar(p)} {p:.0f}%")
c = (d.get("context_window") or {}).get("used_percentage")
if c is not None:
    out.append(f"ctx {c:.0f}%")
print(" · ".join(out))
