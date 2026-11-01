CFLAGS=-Wall -Werror -Wextra -Wpedantic
CLIBS=-lraylib -lglfw3 -lm
CC=gcc

LIBS_PATH=-I./vcpkg_installed/x64-linux/include -L./vcpkg_installed/x64-linux/lib

all: run clean

main:
	$(CC) $(CFLAGS) src/$@.c src/game.c -o $@ $(LIBS_PATH) $(CLIBS)

aigame.so:
	$(CC) -O2 -shared -o $@ -fPIC src/pylib.c src/game.c $(shell python3-config --includes --ldflags) $(LIBS_PATH) $(CLIBS)

run-python: genetic.py clean aigame.so
	uv run $<

run: clean main
	./main

# Binding benchmark: same `aigame` module built five ways (see bindings/README.md)
bindings:
	$(MAKE) -C bindings all

bench: bindings
	$(MAKE) -C bindings bench

.PHONY: clean bindings bench
clean:
	rm -f main aigame.so
