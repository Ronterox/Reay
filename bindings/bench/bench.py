"""Benchmark every `aigame` build: call overhead, code size, artifact size, stubs.

Usage: python bench/bench.py [impl ...]      (writes results.md next to this dir)

Each implementation is measured in its own subprocess because they all export a
module named `aigame` (and each statically links its own raylib + game state).
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDINGS = HERE.parent
ROOT = BINDINGS.parent
BUILD = BINDINGS / "build"

# Hand-written files that make up each binding (shared src/game.c is excluded).
# "glue" = code a human writes to expose the API; "build" = build/packaging config.
SOURCES = {
    "c_capi": {"glue": [ROOT / "src/pylib.c", ROOT / "aigame.pyi"], "build": []},
    "c_cffi": {"glue": ["c_cffi/*.py", "c_cffi/aigame/*.py"], "build": ["c_cffi/Makefile"]},
    "c_nanobind": {"glue": ["c_nanobind/*.cpp"], "build": ["c_nanobind/CMakeLists.txt", "c_nanobind/Makefile"]},
    "rust_pyo3": {
        "glue": ["rust_pyo3/src/*.rs"],
        "build": ["rust_pyo3/Cargo.toml", "rust_pyo3/build.rs", "rust_pyo3/pyproject.toml", "rust_pyo3/Makefile"],
    },
    "zig": {"glue": ["zig/src/aigame.zig", "zig/src/stubgen.zig"], "framework": ["zig/src/py.zig"], "build": ["zig/build.zig", "zig/build.zig.zon", "zig/Makefile"]},
}

# Runs inside the child process; prints one JSON line.
CHILD = r"""
import json, sys, timeit
sys.path.insert(0, sys.argv[1])
import aigame
aigame.init(False)
m = aigame.Vector2(80, 60)
v = aigame.Vector2(1, 2)

def step():
    s = aigame.update(m, False, False)
    return (s.score, s.is_dead, s.player_pos.x, s.player_pos.y, s.safezone.x,
            [(t.x, t.y) for t in s.traps], len(s.cells))

cases = {
    "Vector2(x, y)": lambda: aigame.Vector2(1, 2),
    "v.x read": lambda: v.x,
    "draw() headless": lambda: aigame.draw(m),
    "update()": lambda: aigame.update(m, False, False),
    "update() + read all": step,
}
out = {}
for name, fn in cases.items():
    t = timeit.Timer(fn)
    n, _ = t.autorange()
    n = max(n, 1000)
    best = min(t.repeat(repeat=7, number=n)) / n
    out[name] = best * 1e9  # ns per call
print(json.dumps(out))
"""


def expand(patterns):
    files = []
    for p in patterns:
        if isinstance(p, Path):
            files.append(p)
        else:
            files.extend(sorted(BINDINGS.glob(p)))
    return [f for f in files if f.is_file()]


def sloc(path: Path) -> int:
    """Non-blank lines that are not pure comments."""
    n = 0
    in_block = False
    for line in path.read_text().splitlines():
        s = line.strip()
        if in_block:
            in_block = "*/" not in s
            continue
        if not s or s.startswith(("//", "#")) and not s.startswith(("#include", "#define", "#[")):
            continue
        if s.startswith("/*"):
            in_block = "*/" not in s
            continue
        n += 1
    return n


def artifact(impl: str):
    exts = [p for p in (BUILD / impl).rglob("*.so") if p.is_file()]
    return sum(p.stat().st_size for p in exts)


STUB_ORIGIN = {
    "c_capi": "hand-written",
    "c_cffi": "inline hints (Python shim)",
    "c_nanobind": "generated (nanobind stubgen)",
    "rust_pyo3": "generated (PyO3 introspection)",
    "zig": "generated (own comptime)",
}


def stubs(impl: str) -> str:
    return STUB_ORIGIN.get(impl, "?")


def main(impls):
    rows = {}
    for impl in impls:
        path = BUILD / impl
        if not path.is_dir():
            print(f"skip {impl}: not built", file=sys.stderr)
            continue
        # Best of 3 fresh processes: allocator/ASLR luck moves the allocation-heavy cases by ~30%.
        runs = []
        for _ in range(3):
            r = subprocess.run([sys.executable, "-c", CHILD, str(path)], check=False, capture_output=True, text=True)
            if r.returncode:
                print(f"{impl} failed:\n{r.stderr}", file=sys.stderr)
                break
            runs.append(json.loads(r.stdout))
        if len(runs) < 3:
            continue
        src = SOURCES.get(impl, {"glue": [], "build": []})
        rows[impl] = {
            "timings": {case: min(run[case] for run in runs) for case in runs[0]},
            "glue_sloc": sum(sloc(f) for f in expand(src["glue"])),
            "build_sloc": sum(sloc(f) for f in expand(src["build"])),
            "framework_sloc": sum(sloc(f) for f in expand(src.get("framework", []))),
            "so_kib": artifact(impl) / 1024,
            "stubs": stubs(impl),
        }
        print(f"measured {impl}", file=sys.stderr)

    if not rows:
        sys.exit("nothing measured")
    cases = list(next(iter(rows.values()))["timings"])
    lines = ["# aigame binding benchmark", "", "## Call overhead (ns/call, best of 7 repeats x 3 processes, lower is better)", ""]
    lines.append("| case | " + " | ".join(rows) + " |")
    lines.append("|---|" + "---:|" * len(rows))
    for c in cases:
        lines.append(f"| {c} | " + " | ".join(f"{rows[i]['timings'][c]:.0f}" for i in rows) + " |")
    lines += ["", "## Size", "", "| metric | " + " | ".join(rows) + " |", "|---|" + "---:|" * len(rows)]
    lines.append("| binding glue SLOC | " + " | ".join(str(rows[i]["glue_sloc"]) for i in rows) + " |")
    lines.append("| own framework SLOC (reusable) | " + " | ".join(str(rows[i]["framework_sloc"]) for i in rows) + " |")
    lines.append("| build config SLOC | " + " | ".join(str(rows[i]["build_sloc"]) for i in rows) + " |")
    lines.append("| extension size (KiB) | " + " | ".join(f"{rows[i]['so_kib']:.0f}" for i in rows) + " |")
    lines.append("| type stubs | " + " | ".join(rows[i]["stubs"] for i in rows) + " |")
    md = "\n".join(lines) + "\n"
    (BINDINGS / "results.md").write_text(md)
    (BINDINGS / "results.json").write_text(json.dumps(rows, indent=2))
    print(md)


if __name__ == "__main__":
    main(sys.argv[1:] or list(SOURCES))
