# Build the PyO3 extension + its auto-generated stub into ../build/rust_pyo3/.
# `maturin generate-stubs` runs the release cargo build itself, then reads the
# introspection data PyO3's `experimental-inspect` feature embedded in the .so.
# (maturin moves the built cdylib to target/maturin/.)
ROOT := $(abspath ../..)
PY   := $(ROOT)/.venv/bin/python
OUT  := ../build/rust_pyo3

all:
	$(ROOT)/.venv/bin/maturin generate-stubs --profile release -i $(PY) --out target/stubs
	mkdir -p $(OUT)
	cp target/maturin/libaigame.so $(OUT)/aigame.so
	cp target/stubs/aigame/__init__.pyi $(OUT)/aigame.pyi

clean:
	cargo clean
	rm -rf $(OUT)

.PHONY: all clean
