# c_cffi: cffi API mode (out-of-line) + thin pure-Python package

## Approach
- `build_ffi.py`: `ffi.cdef(...)` + `ffi.set_source("aigame._aigame_cffi", '#include "game.h"', sources=[src/game.c], ...)`.
  Compiles game.c into one extension `aigame/_aigame_cffi*.so` (raylib/glfw linked statically).
- `aigame/__init__.py`: plain Python. cffi only yields cdata, so `Vector2` (`__slots__`, `operator.index` validation,
  `__reduce__` for pickle) and `GameState` (`@dataclass(slots=True)`) are Python classes; `update/draw/init/close` marshal to C.
- The C `static State` lives in Python as `ffi.new("State *")`; `init()` does `_state[0] = lib.InitGame()`.
  Mouse is a reusable by-value `Vector2` cdata (`ffi.new("Vector2 *")[0]`), mutated in place per call.
- `update()` reads traps with one `ffi.unpack(float*, 20)` instead of 20 cdata field reads.
- Typing: the hints in `__init__.py` ARE the stub; no `.pyi` shipped (add an empty `py.typed` only if published as a lib).
  Annotations are not enforced by cffi; runtime validation is hand-written (`index()` for ints, `isinstance` for mouse).
- Build: `make -C bindings/c_cffi` -> `bindings/build/c_cffi/aigame/{__init__.py,_aigame_cffi*.so}`; compile happens in a temp
  dir, so no `.c`/`.o` land in the source tree. Cold build ~0.5-0.7 s (game.c is small, raylib is prebuilt).

## Duplicated from the C headers (drift risk)
Hand-copied into `cdef`:
- `struct Vector2 {float x, y}` (raylib.h), `struct State` (all 7 fields, `TRAPS_AMOUNT` hard-coded as `[10]`),
- prototypes of `Update`, `Draw`, `InitGameWindow`, `InitGame`, plus raylib's `IsWindowReady`, `CloseWindow`.
- `uint` (glibc typedef) had to be spelled `unsigned int`; `bool` is accepted as-is.
Constants: `#define TRAPS_AMOUNT ...` works (integer macro). `SCREEN_WIDTH 800.` / `CELLS_LIMIT 5.` are doubles:
`#define SCREEN_WIDTH ...` compiles to `_cffi_const_SCREEN_WIDTH` and fails with
`error: invalid operands to binary | (have 'double' and 'int')`. Workaround: define `static const int SCREEN_WIDTH_I = (int)SCREEN_WIDTH;`
in the `set_source` C prelude and declare it as `static const int` in cdef (a second duplicated name per constant).
Drift detection is uneven: a renamed/missing field is a hard C compile error (`'Vector2' has no member named 'yy'`),
but a wrong field *type* (`double y` vs `float y`) is only a `-Wincompatible-pointer-types` warning, the build succeeds and
`import` raises nothing. I did not verify whether a changed array length or an extra/missing trailing field is detected; assume only the test suite
(golden trace) catches those.

## Friction points
- cffi can't parse `game.h` (needs raylib.h, `#define` expression macros like `SIZEW SCREEN_WIDTH / CELLS_LIMIT`), hence duplication.
- `ffi.compile(tmpdir=...)` chdirs into tmpdir: relative `include_dirs`/`sources` fail with `fatal error: game.h: No such file or directory`.
  Use absolute paths.
- Nothing in cffi gives you classes: `Vector2`, `GameState`, repr, pickling, int-only validation, TypeError on bad mouse are all
  hand-written Python (about 50 lines); behaviour parity with the C-API module is by test, not by construction.
- By-value struct args need a real cdata struct (no tuple/dict shortcut), hence the shared `_mouse` object. Not re-entrant/thread-safe.
- Float->int truncation of positions (`int(...)`) is done in Python to mimic the C-API implicit cast.
- The `.so` exports all ~1200 raylib symbols (static libs linked into a shared object); same as the C-API build.

## Where overhead shows (bench: Vector2(), attr read, draw(), update(), update()+read)
- `Vector2()` ctor and attr read: pure Python (`__slots__`, `operator.index` x2) -> slower than a C type for the ctor
  (Python frame + 2 calls); attr read is as fast as any slotted attribute.
- `draw()`: Python wrapper + `isinstance` + 2 cdata field stores + `IsWindowReady()` call + (if window) `Draw()`: ~4 FFI crossings;
  headless this is dominated by wrapper overhead, not C.
- `update()`: biggest cost. Builds 25 cells + 10 traps + 2 vectors + dataclass in Python (~38 Vector2 `__init__` calls,
  each with `operator.index`), plus cdata field reads (`safeZone`, `spritePos`, `isDead`, `score`) - each cdata attribute read allocates
  Python objects. The C call itself is cheap. `update()+read` adds nothing (everything is already materialised Python objects).
