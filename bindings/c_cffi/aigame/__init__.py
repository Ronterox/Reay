"""aigame: pure-Python wrapper over the cffi module `_aigame_cffi` (game.c)."""

from dataclasses import dataclass
from operator import index

from ._aigame_cffi import ffi, lib

SCREEN_WIDTH: int = lib.SCREEN_WIDTH_I
SCREEN_HEIGHT: int = lib.SCREEN_HEIGHT_I
CELLS_LIMIT: int = lib.CELLS_LIMIT_I
TRAPS_AMOUNT: int = lib.TRAPS_AMOUNT

_state = ffi.new("State *")  # the C `static State state` lives in Python here
_traps = ffi.cast("float *", _state.trapPositions)  # flat x0,y0,x1,y1,... view
_mouse = ffi.new("Vector2 *")[0]  # reusable by-value argument


class Vector2:
    __slots__ = ("x", "y")
    x: int
    y: int

    def __init__(self, x: int, y: int) -> None:
        self.x = index(x)  # TypeError for float/str/None, like the C "i" format
        self.y = index(y)

    def __repr__(self) -> str:
        return f"Vector2({self.x}, {self.y})"

    def __reduce__(self):
        return (Vector2, (self.x, self.y))


@dataclass(slots=True)
class GameState:
    cells: list[Vector2]
    traps: list[Vector2]
    safezone: Vector2
    player_pos: Vector2
    is_dead: bool
    score: int


def _set_mouse(mouse: Vector2) -> None:
    if not isinstance(mouse, Vector2):
        raise TypeError("Expected a Vector2 object")
    _mouse.x = mouse.x
    _mouse.y = mouse.y


def update(mouse: Vector2, click: bool, reset: bool) -> GameState:
    _set_mouse(mouse)
    lib.Update(_state, _mouse, bool(click), bool(reset))
    t = ffi.unpack(_traps, 2 * TRAPS_AMOUNT)  # one FFI call instead of 20 field reads
    s = _state
    return GameState(
        cells=[Vector2(i, j) for i in range(CELLS_LIMIT) for j in range(CELLS_LIMIT)],
        traps=[Vector2(int(t[k]), int(t[k + 1])) for k in range(0, 2 * TRAPS_AMOUNT, 2)],
        safezone=Vector2(int(s.safeZone.x), int(s.safeZone.y)),
        player_pos=Vector2(
            int(s.spritePos.x / (SCREEN_WIDTH / CELLS_LIMIT)), int(s.spritePos.y / (SCREEN_HEIGHT / CELLS_LIMIT))
        ),
        is_dead=s.isDead,
        score=s.score,
    )


def draw(mouse: Vector2) -> None:
    _set_mouse(mouse)
    if lib.IsWindowReady():
        lib.Draw(_state, _mouse)


def init(render: bool = True) -> None:
    if render and not lib.IsWindowReady():
        lib.InitGameWindow()
    _state[0] = lib.InitGame()


def close() -> None:
    if lib.IsWindowReady():
        lib.CloseWindow()
