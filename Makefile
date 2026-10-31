CFLAGS=-Wall -Werror -Wextra -Wpedantic
CLIBS=-lraylib -lglfw3 -lm
CC=gcc

LIBS_PATH=-I./vcpkg_installed/x64-linux/include -L./vcpkg_installed/x64-linux/lib

all: run clean

main:
	$(CC) $(CFLAGS) src/$@.c -o $@ $(LIBS_PATH) $(CLIBS)

aigame.so:
	$(CC) -shared -o $@ -fPIC src/pylib.c $(shell python3-config --includes --ldflags) $(LIBS_PATH) $(CLIBS)

run-python: genetic.py clean aigame.so
	uv run $<

run: clean main
	./main

.PHONY: clean
clean:
	rm -f main aigame.so
