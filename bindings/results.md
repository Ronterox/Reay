# aigame binding benchmark

## Call overhead (ns/call, best of 7 repeats x 3 processes, lower is better)

| case | c_capi | c_cffi | c_nanobind | rust_pyo3 | zig |
|---|---:|---:|---:|---:|---:|
| Vector2(x, y) | 162 | 272 | 175 | 164 | 154 |
| v.x read | 67 | 57 | 78 | 75 | 73 |
| draw() headless | 132 | 467 | 99 | 112 | 93 |
| update() | 840 | 13183 | 501 | 1990 | 833 |
| update() + read all | 2149 | 14115 | 5431 | 3925 | 2354 |

## Size

| metric | c_capi | c_cffi | c_nanobind | rust_pyo3 | zig |
|---|---:|---:|---:|---:|---:|
| binding glue SLOC | 176 | 111 | 61 | 117 | 60 |
| own framework SLOC (reusable) | 0 | 0 | 0 | 0 | 392 |
| build config SLOC | 0 | 12 | 27 | 59 | 49 |
| extension size (KiB) | 1382 | 1365 | 1356 | 1848 | 1488 |
| type stubs | hand-written | inline hints (Python shim) | generated (nanobind stubgen) | generated (PyO3 introspection) | generated (own comptime) |
