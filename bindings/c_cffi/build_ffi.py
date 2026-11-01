"""Build the cffi extension `aigame._aigame_cffi` (API mode, out-of-line).

cffi cannot parse game.h (it includes raylib.h, uses `uint`, macros-with-operators),
so the pieces of the C API we call are re-declared by hand in CDEF below.
"""

import sys
from pathlib import Path

from cffi import FFI

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VCPKG = ROOT / "vcpkg_installed" / "x64-linux"
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "build"

ffi = FFI()

# DUPLICATED from src/game.h / raylib.h -- keep in sync by hand. cffi checks the
# declarations against the real headers at compile time (field names, types, sizes,
# offsets), so drift fails the build instead of silently corrupting memory.
ffi.cdef(
    """
    typedef struct Vector2 { float x; float y; } Vector2;      // raylib.h
    typedef struct State {                                       // game.h
        Vector2 playerPos;
        Vector2 spritePos;
        bool isDead;
        Vector2 trapPositions[10];                               // TRAPS_AMOUNT
        Vector2 trapSize;
        Vector2 safeZone;
        unsigned int score;                                      // `uint` is a glibc typedef
    } State;

    void Update(State *s, const Vector2 mouse, const bool click, const bool reset);
    void Draw(State *s, const Vector2 mouse);
    void InitGameWindow(void);
    State InitGame(void);
    bool IsWindowReady(void);                                    // raylib.h
    void CloseWindow(void);                                      // raylib.h

    #define TRAPS_AMOUNT ...                                     // integer macro: fine
    """
)

# Double macros (800., 5.) can't be `#define X ...` in cdef (cffi needs an integer),
# so export them through integer wrappers computed by the C compiler.
ffi.cdef("static const int SCREEN_WIDTH_I, SCREEN_HEIGHT_I, CELLS_LIMIT_I;")

ffi.set_source(
    "aigame._aigame_cffi",
    """
    #include "game.h"
    static const int SCREEN_WIDTH_I = (int)SCREEN_WIDTH;
    static const int SCREEN_HEIGHT_I = (int)SCREEN_HEIGHT;
    static const int CELLS_LIMIT_I = (int)CELLS_LIMIT;
    """,
    sources=[str(ROOT / "src" / "game.c")],
    include_dirs=[str(ROOT / "src"), str(VCPKG / "include")],
    library_dirs=[str(VCPKG / "lib")],
    libraries=["raylib", "glfw3", "m"],
    extra_compile_args=["-O2"],
)

if __name__ == "__main__":
    ffi.compile(tmpdir=str(OUT), verbose=False)
