# Binding benchmark: one C game, five Python bindings

The same `aigame` module (`Vector2`, `GameState`, `update/draw/init/close`, 4 constants) built on top of the
unchanged C core (`src/game.h` + `src/game.c`) five ways:

| impl | what it is |
|---|---|
| `c_capi` | the original hand-written CPython C API module (`src/pylib.c` + hand-written `aigame.pyi`) |
| `c_cffi` | cffi API mode, compiled out-of-line + a small pure-Python shim package |
| `c_nanobind` | nanobind (C++17) wrapping the C header, CMake, auto stubgen |
| `rust_pyo3` | PyO3 0.30 macros + bindgen on `game.h` + `cc` for `game.c`, built by maturin 1.16 |
| `zig` | Zig 0.16 `@cImport` of `Python.h` and `game.h` + a ~400-line comptime layer (`zig/src/py.zig`) |

All five pass the same 22-test contract in `tests/` (types, errors, pickling, and a 400-step golden trace that
must match the C-API build bit for bit).

```sh
make -C bindings          # build all into bindings/build/<impl>/
make -C bindings test     # run the contract against each
make -C bindings bench    # regenerate results.md
```

Each implementation directory has a `NOTES.md` with the detailed friction log (exact errors, workarounds).

## Results (Python 3.10, x86-64, gcc 11 / rustc 1.91 / zig 0.16)

Call overhead, ns/call (best of 7 repeats × 3 processes, lower is better):

| case | c_capi | c_cffi | c_nanobind | rust_pyo3 | zig |
|---|---:|---:|---:|---:|---:|
| `Vector2(x, y)` | 162 | 272 | 175 | 164 | 154 |
| `v.x` read | 67 | 57 | 78 | 75 | 73 |
| `draw()` headless | 132 | 467 | 99 | 112 | 93 |
| `update()` | 840 | 13183 | 501 | 1990 | 833 |
| `update()` + read all fields | 2149 | 14115 | 5431 | 3925 | 2354 |

Effort and output:

| | c_capi | c_cffi | c_nanobind | rust_pyo3 | zig |
|---|---:|---:|---:|---:|---:|
| module glue SLOC | 176¹ | 111 | 61 | 117 | 60 |
| reusable framework you write yourself | – | – | – | – | 392 |
| build config SLOC | 1 line² | 12 | 27 | 59 | 49 |
| clean build (warm toolchain caches) | 0.2 s | 0.4 s | 3.6 s | 12.6 s³ | 2.3 s⁴ |
| rebuild after editing glue | 0.3 s | 0.5 s | 1.4 s | 0.9 s | 0.6 s |
| `.so` size | 1382 KiB | 1365 KiB | 1356 KiB | 1848 KiB | 1488 KiB |
| type stubs | hand-written | inline hints in shim | generated | generated | generated (comptime) |
| `stubtest` vs runtime | 10 errors (6 real)⁵ | n/a (it *is* Python) | 9 (stubtest/nanobind false positives) | **0** | 4 (missing `@final`) |
| reads the C header itself? | yes (`#include`) | **no**, `State` + prototypes re-declared | yes (`extern "C"`) | yes (bindgen) | yes (`@cImport`) |

¹ 147 lines of C + 29 lines of hand-maintained `.pyi`.
² one `gcc` line in the top Makefile. ³ most of it is bindgen + its libclang deps; `target/` is 163 MB.
⁴ the very first Zig build on a machine costs ~60 s while it builds its own libc pieces.
⁵ the hand-written stub declares `GameState` as a `@dataclass` with a constructor that doesn't exist at runtime.

## What each one actually feels like

**Hand-written C API.** Everything is explicit: `PyTypeObject`, `PyMemberDef` offset tables, refcounts,
`PyArg_ParseTuple` format strings. It works and it's fast, but the stub is a second source of truth, and here
it had already drifted: `aigame.pyi` describes a `GameState` constructor that doesn't exist.

**cffi.** It doesn't solve the problem you care about. cffi gives you C structs as `cdata`, not Python
classes, so you still hand-write `Vector2`/`GameState` in Python. It also can't parse `game.h` (raylib
includes, macros), so `State` and the prototypes get **copied into a Python string**. A wrong field type
there is only a C compiler *warning*. The double macros (`#define SCREEN_WIDTH 800.`) need
a `static const int` shim. The upside is zero native glue, and the types come free because the shim is Python.
The downside is runtime: building 37 Python objects per `update()` makes it **~15× slower** than everything
else. cffi suits "call a C function with numbers", not "expose a typed object model".

**nanobind (C++).** This is the closest thing to "the framework for C". `nb::class_<T>().def_rw(...)`, `nb::init<int,int>()`
with `nb::arg`, and `nanobind_add_stub` generates a stub that is more accurate than the hand-written one.
It needs the fewest glue lines of anything except Zig's module file. The costs are that you're writing C++, CMake is mandatory,
STL casters are opt-in headers (forget `<nanobind/stl/string.h>` and you get a *runtime* error), and the `bool`
caster is strict, so the truthiness workaround drops to the raw C API and the stub says `object`.
`std::vector` members are copied to a fresh `list` on **every** attribute access. That's why `update()` is
the fastest here (lazy) but "update + read" is 2.5× slower than C.

**Rust / PyO3.** These are the macros you were hoping for. `#[pyclass(get_all, set_all)]`, `#[pyfunction]`,
`#[pyo3(signature = (render = true))]`, and `#[pymodule] mod aigame { ... }`. Pickling is a 3-line
`__getnewargs__`. bindgen read `game.h` on the first try (double macros became `f64` constants, `uint` became `c_uint`)
and adds compile-time layout assertions. Its stub is the **only one that passes `stubtest` with zero issues**,
and it comes from PyO3's own `experimental-inspect` + `maturin generate-stubs`, with no annotations needed.
The C `static State` turns into a `Mutex<State>`, because Rust makes you say what you mean about global state.
The costs are the heaviest build (clean 12–17 s, 163 MB `target/`), the same strict-`bool` surprise as nanobind, and
`Vec<Py<T>>` fields that rebuild a list on every access.

**Zig.** This one comes closest to 1:1, but you build the framework yourself. `@cImport` swallows `Python.h` and `game.h`
whole, and `zig/src/aigame.zig` reads almost like the `.pyi`:

```zig
pub const Vector2 = struct { x: i32, y: i32 };
pub const GameState = struct { cells: [CELLS_LIMIT * CELLS_LIMIT]Vector2, traps: [TRAPS_AMOUNT]Vector2, ... };
pub fn init(a: struct { render: bool = true }) void { ... }
comptime { py.exportModule(@This(), "aigame"); }
```

From those plain declarations, `py.zig` uses `@typeInfo` at comptime to generate the type objects, member tables,
argument parsing, conversions, *and the `.pyi` text itself*, so the stub can't drift from the code. Its
runtime matches the hand-written C. The gaps:
- **No maintained framework for Zig 0.16.** ziggy-pydust pins Zig 0.15 and is largely dormant, so you write
  the ~400-line `py.zig` once yourself (it's reusable across modules).
- **`@typeInfo` doesn't expose parameter names**, so functions take a struct of named args
  (`fn init(a: struct { render: bool = true })`). It's a little odd, but it's also how defaults get expressed.
- **translate-c chokes on CPython's initializer macros** (`PyObject_HEAD`, `PyVarObject_HEAD_INIT`,
  `Py_RETURN_NONE`, `PyMODINIT_FUNC`, …). About 10 lines of manual workarounds, documented in `zig/NOTES.md`.
- Zig's build/std APIs churn every release.

## Verdict

| if you want… | pick |
|---|---|
| a binding for C code with the least friction today | **nanobind**: shortest glue, generated stubs, fast. You'll write a little C++. |
| the most "it just knows the types" experience | **PyO3**: macros + bindgen + introspected stubs, the only stub with no `stubtest` issues. Slowest build. |
| the closest to 1:1 with the C, and the most fun | **Zig comptime**: declarations *are* the API and the stub, at C-API speed. You own the framework. |
| to call a few C functions on numbers | **cffi**. Not for exposing typed objects. |
| to learn how CPython really works | the hand-written C API you already did. Every framework above is generating that. |

One cross-cutting lesson: the first step for every option was splitting `main.c` into `game.h`/`game.c`.
A clean header is the real "binding API"; the five tools only differ in how much of it they can read.
