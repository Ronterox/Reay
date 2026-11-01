# Build the same `aigame` Python module five different ways, then test + benchmark them.
#   make            build every implementation into build/<impl>/
#   make test       run the shared conformance suite against each build
#   make bench      runtime + code-size benchmark -> results.md
ROOT    := $(abspath ..)
PY      := $(ROOT)/.venv/bin/python
VCPKG   := $(ROOT)/vcpkg_installed/x64-linux
CFLAGS  := -O2 -fPIC -Wall -Wextra -I$(ROOT)/src -I$(VCPKG)/include
LDLIBS  := -L$(VCPKG)/lib -lraylib -lglfw3 -lm
PYINC   := $(shell python3-config --includes)

IMPLS   := c_capi c_cffi c_nanobind rust_pyo3 zig

all: $(IMPLS)

# 1. Hand-written CPython C API (the original src/pylib.c)
c_capi:
	mkdir -p build/$@
	gcc -shared $(CFLAGS) $(PYINC) $(ROOT)/src/pylib.c $(ROOT)/src/game.c -o build/$@/aigame.so $(LDLIBS)
	cp $(ROOT)/aigame.pyi build/$@/aigame.pyi

c_cffi:
	$(MAKE) -C c_cffi

c_nanobind:
	$(MAKE) -C c_nanobind

rust_pyo3:
	$(MAKE) -C rust_pyo3

zig:
	$(MAKE) -C zig

test:
	@for impl in $(IMPLS); do \
		echo "=== $$impl ==="; \
		AIGAME_IMPL=$$impl $(PY) -m pytest -q tests || exit 1; \
	done

golden: c_capi
	$(PY) tests/game_trace.py

bench:
	$(PY) bench/bench.py $(IMPLS)

clean:
	rm -rf build

.PHONY: all test golden bench clean $(IMPLS)
