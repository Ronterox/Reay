# c_nanobind

nanobind 3.1.0 (C++17 glue, `game.h` included via `extern "C"`, `game.c` compiled as C by the same CMake target).

## Approach
- Separate C++ structs: `Vec {int x,y}` (Python `Vector2`; raylib's is `float`) and `GameState {std::vector<Vec> cells, traps; Vec safezone, player_pos; bool is_dead; int score;}`. The C `State` stays a file-static, as in `pylib.c`.
- `nb::class_` + `.def_rw`, `nb::init<int,int>()` + `nb::arg`, lambda `__repr__`, `__getstate__/__setstate__` (placement-new, the documented nanobind pickling recipe), `m.attr(...)` for int constants.
- `def_rw` on `std::vector<Vec>` (with `nanobind/stl/vector.h`) returns a fresh `list` of `Vector2` on every access, so `type(s.cells) is list` holds. Cost: a copy per access, and `s.cells.append(x)` does not mutate the state (pylib.c returns the stored list, so it would). Setter takes any `Sequence[Vector2]`.
- `nanobind_add_stub` generates `aigame.pyi` during the build.

## Automatic vs manual
- Automatic: int/bool/tuple/list conversions, kwargs + arg-count + type errors (`TypeError` for `Vector2(1.5, 2)`, `update((0,0), ...)`, `draw(None)`), refcounting, GameState allocation/dealloc, `__module__`/`__name__`, stub, docstrings, default args (`render=True`).
- Manual: building the `GameState` from the C `State` (same logic as pylib.c, minus all PyList/PyObject code), the int-vs-float Vector2 split, `__repr__`, pickling, constants, truthiness workaround.

## Stub vs hand-written `aigame.pyi`
Generated one is more accurate: real `__init__`, properties with setters, `render: bool = True`, `-> None`, constants with values, docstrings; the hand-written one has `@dataclass` (not true at runtime), no `__repr__`, and `draw`/`close` lack return types. Differences: `click`/`reset` are typed `object` (see below); setters appear as positional-only `arg`; list setters are `Sequence[Vector2]`.

## Size
`aigame.cpp` 62 SLOC (vs 176 for `pylib.c`), `CMakeLists.txt` 17, `Makefile` 12.

## Build time (g++ 11, Ninja, wall clock)
- Clean (`make clean && make`, includes libnanobind-static, game.c, glue, stub): ~3.9 s wall (~22 s CPU)
- Incremental (touch `aigame.cpp`): ~1.5 s (recompile glue, relink, regenerate stub)

## Friction points
1. **Strict `bool` caster**: `update(v, 0, 1)` fails with `TypeError: update(): incompatible function arguments ... click: bool, reset: bool ... Invoked with types: aigame.Vector2, int, int`. nanobind never coerces ints to bool (C-API `"p"` does). Fix: take `nb::handle` and call `PyObject_IsTrue` -- drops back to the raw C-API and the stub says `object` instead of `bool` (a `nb::sig(...)` override would fix the stub but adds more glue).
2. **STL casters are opt-in headers**: forgetting `nanobind/stl/string.h` compiles fine, then fails at runtime: `TypeError: Unable to convert function return value to a Python type! The signature was __repr__(self) -> std::__cxx11::basic_string<char, ...>` (and the stub contained that mangled type). Same trap for `vector.h`/`tuple.h`.
3. **C header in C++**: `game.h`'s `Vec2(x, y)` macro (`(struct Vector2){x, y}` compound literal) is C-only style, so the glue builds `Vector2{(float)x, (float)y}` directly; `game.h` needs `extern "C"` wrapping. Macro constants are doubles (`800.`) so they need `(int)` casts.
4. **Value semantics**: `GameState` fields are copies; nanobind's `def_rw` on vectors yields a new list per access (no aliasing). Fine for this API, but not a view of C memory.
5. **Build config is bigger than usual**: needs CMake + Ninja + `python -m nanobind --cmake_dir` lookup, and a C+CXX project. The stub step imports the built module, so it runs at build time (not available when cross-compiling).
6. Everything else (class binding, ctor kwargs, pickling, errors) worked on first compile.
