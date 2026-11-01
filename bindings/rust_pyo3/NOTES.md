# rust_pyo3: notes

## Approach
- `build.rs` compiles `src/game.c` with the `cc` crate, links static `raylib` + `glfw3` + `-lm`, and runs
  `bindgen` on `game.h` to produce `ffi::{State, Vector2, Update, Draw, ...}`.
- `src/lib.rs` (117 SLOC after rustfmt) is a declarative `#[pymodule] mod aigame { ... }` holding
  `#[pyclass]`/`#[pymethods]`/`#[pyfunction]` items plus `#[pymodule_export] const`s.
- `make` runs `maturin generate-stubs --profile release`, which does the cargo build and writes the stub.
  The Makefile then copies `target/maturin/libaigame.so` to `../build/rust_pyo3/aigame.so` and
  `target/stubs/aigame/__init__.pyi` to `aigame.pyi`.
- Toolchain: pyo3 0.30.1, maturin 1.16.0, bindgen 0.73.2, cc 1.x, rustc 1.91.1, edition 2024.
  Result: 22/22 conformance tests pass.

## What the macros automated vs what stayed manual
Automated (each one replaces a block of C-API code in `pylib.c`):
- Type objects, `PyType_Ready`, module creation, and `PyModule_AddObject`/`AddIntConstant` come from `#[pymodule] mod` + `#[pymodule_export]`.
- `PyMemberDef` tables come from `#[pyclass(get_all, set_all)]`.
- Argument parsing (`PyArg_ParseTuple*`, keyword lists, arity and type errors) and `Convert_Vector2` come from the function signature. A `PyRef<Vector2>` parameter type-checks the argument by itself.
- Refcounting and dealloc come from `Py<T>`/`Bound<T>` RAII.
- Setting `__module__ = "aigame"` happens automatically for classes declared inside the declarative module, which pickle needs.
- Default arguments come from `#[pyo3(signature = (render = true))]`.

Manual:
- `__repr__` (a single `format!`) and pickling. I used `__getnewargs__ -> (i32, i32)` instead of `__reduce__` because it is shorter and gets a clean type in the stub.
- **Truthiness for `click`/`reset`.** PyO3's `bool` extraction is strict: `init(0)` raises
  `TypeError: 'int' object is not an instance of 'bool'`. The C baseline's `"p"` accepts any object, so
  `update` takes `&Bound<PyAny>`, calls `.is_truthy()?`, and declares `click: "bool"` in the signature so the
  stub stays typed. `init(render: bool)` keeps the strict `bool`, which is a small divergence: `init(0)` raises a TypeError here but works in the C version.
- Building the `GameState` from the C `State`: float to int casts and the `player_pos` division.

## bindgen
It worked on the first try: no blocklists or tweaks, just an allowlist so it doesn't emit all of `raylib.h`.
- Double macros: `#define SCREEN_WIDTH 800.` becomes `pub const SCREEN_WIDTH: f64 = 800.0;` and `TRAPS_AMOUNT` becomes `u32`.
  The expression macros (`SIZEW` etc.) are skipped, which is fine because they are allowlisted out anyway. Python wants ints, so the
  binding re-exports them as `const SCREEN_WIDTH: i32 = ffi::SCREEN_WIDTH as i32;`. A float-to-int `as` cast is allowed in a const.
- `uint` (from `<sys/types.h>`) becomes `pub type uint = c_uint;`. C `bool` maps to Rust `bool` directly.
- `bindgen` emits compile-time size and offset assertions for `State` (120 bytes), so ABI drift fails the build.
- libclang 14 at `/usr/lib/llvm-14` was found without setting `LIBCLANG_PATH`.
- Cost: bindgen, clang-sys, regex and similar crates are build-dependencies and make up most of the clean build time. They only run once.

## Global state
`static STATE: Mutex<ffi::State> = Mutex::new(unsafe { std::mem::zeroed() });`
This mirrors C's zero-initialised `static State`. `mem::zeroed` is `const`, and the bindgen struct is POD and therefore `Send`.
Rust 2024 denies references to a `static mut`, so a `Mutex` is the idiomatic choice. `update` copies the `State` out (bindgen derives `Copy`)
and releases the lock before it builds any Python objects, so no Python code runs while the lock is held.
`unsafe` appears only around the FFI calls and the zeroed initialiser.

## Stub generation: automatic, and it works
I used PyO3's own **`experimental-inspect`** feature with `maturin generate-stubs`, and did not need the
`pyo3-stub-gen` crate. pyo3-stub-gen 0.23.2 does resolve against pyo3 0.30.1, but it needs `#[gen_stub_*]` on every item, a
`stub_gen` binary, `module_variable!` duplicates for the constants, and an `rlib` crate type. experimental-inspect needs none of that: the stub carries zero extra
glue lines. The only addition is the `"bool"` annotation on the `update` signature.
- `stubtest aigame` (mypy) reports `Success: no issues found`. pyright and mypy --strict both resolve `s.cells` to `list[Vector2]`,
  `s.is_dead` to `bool` and `SCREEN_WIDTH` to `int`, and both flag `Vector2("a", 1)`, `draw((0, 0))` and `update(v, 1, 0)`.
- The generated stub is more precise than the hand-written one:
  - Classes are `@final`.
  - Constants are `Final[int]`.
  - Parameters are `SupportsIndex` and correctly positional-only (`/`).
  - Properties come with setters.
  - Docstrings come from `///` comments.
- Quirks:
  - String annotations from `signature` stay quoted (`click: "bool"`).
  - The setter for a list field is typed `SupportsGetItem[int, Vector2]` from `_typeshed`.
  - The output always uses package layout (`aigame/__init__.pyi`).
  - It requires the declarative `#[pymodule] mod` form. A `fn`-style module is marked `Incomplete`.

## Build times (12 cores; crates already downloaded)
| scenario | wall |
|---|---|
| clean (`cargo clean && make`) | 17.0 s (33 crates incl. build-deps) |
| touch `src/lib.rs` | 1.3 s |
| touch `src/game.c` (cc + bindgen re-run) | 1.8 s |
| no-op `make` | 0.4 s |

The first `cargo` invocation also fetched about 130 crates from crates.io. That time is not counted above. `target/` reaches 163 MB.

## Surprises / friction
- `maturin generate-stubs --release` fails with `error: unexpected argument '--release' found`. You have to pass `--profile release`.
- maturin moves the built cdylib to `target/maturin/libaigame.so`. After a maturin build, `target/release/libaigame.so` does not exist
  (`cp: cannot stat 'target/release/libaigame.so'`).
- Alternating `cargo build` and maturin rebuilds `pyo3-ffi` and `pyo3` each time, because maturin sets `PYO3_PYTHON` and related variables.
  The Makefile therefore only uses maturin.
- Strict `bool` extraction (see above) is the only place where the "obvious" PyO3 code didn't match C-API behaviour.
- Semantic difference: `#[pyo3(get)]` on `Vec<Py<Vector2>>` builds a **new list on each attribute access**, so
  `s.cells is s.cells` is `False` and `s.cells.append(...)` is lost. The C version stores one list object. Storing
  `Py<PyList>` would match C, but then the stub degrades to plain `list`. I kept `Vec` for the typed stub. No test depends on this.
- `GameState()` raises `TypeError: cannot create 'aigame.GameState' instances` because no `#[new]` is defined.
  The C type allows `GameState()` through `PyType_GenericNew`, which gives fields set to `None`.
