# Build aigame.so + aigame.pyi into ../build/zig (zig build installs straight into that prefix).
OUT   := $(abspath ../build/zig)
PYINC := $(shell python3 -c 'import sysconfig; print(sysconfig.get_paths()["include"])')

all:
	zig build -Doptimize=ReleaseFast -Dpython-include=$(PYINC) -p $(OUT)

clean:
	rm -rf .zig-cache zig-out $(OUT)

.PHONY: all clean
