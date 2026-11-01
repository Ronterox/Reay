# nanobind build: CMake + Ninja in build-cmake/, then copy the .so + generated .pyi.
PY    := $(abspath ../../.venv/bin/python)
BUILD := build-cmake
OUT   := ../build/c_nanobind

all:
	cmake -S . -B $(BUILD) -G Ninja -DPython_EXECUTABLE=$(PY)
	cmake --build $(BUILD)
	mkdir -p $(OUT)
	cp $(BUILD)/aigame*.so $(BUILD)/aigame.pyi $(OUT)/

clean:
	rm -rf $(BUILD) $(OUT)

.PHONY: all clean
