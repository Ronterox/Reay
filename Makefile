CFLAGS=-Wall -Werror -Wextra -Wpedantic
CLIBS=-lraylib -lglfw3 -lm
CC=gcc

LIBS_PATH=-I./vcpkg_installed/x64-linux/include -L./vcpkg_installed/x64-linux/lib

all: run clean

main:
	$(CC) $(CFLAGS) src/main.c -o main $(LIBS_PATH) $(CLIBS)

run: main
	./main

clean:
	rm -f main
