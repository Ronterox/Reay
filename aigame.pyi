# {"update", update, METH_NOARGS, "Updates the game"},
# {"draw", draw, METH_NOARGS, "Draws the game"},
# {"init", init, METH_NOARGS, "Initializes the game"},
# {"close", close_window, METH_NOARGS, "Closes the window"},

# typedef struct {
# 	PyObject_HEAD;
# 	PyObject *cells;	  // List of Vector2
# 	PyObject *traps;	  // List of Vector2
# 	PyObject *safezone;	  // Vector2
# 	PyObject *player_pos; // Vector2
# 	int score;
# } GameStateObject;

# PyModule_AddIntConstant(m, "SCREEN_WIDTH", SCREEN_WIDTH);
# PyModule_AddIntConstant(m, "SCREEN_HEIGHT", SCREEN_HEIGHT);
# PyModule_AddIntConstant(m, "CELLS_LIMIT", CELLS_LIMIT);
# PyModule_AddIntConstant(m, "TRAPS_AMOUNT", TRAPS_AMOUNT);

from dataclasses import dataclass

SCREEN_WIDTH = 0
SCREEN_HEIGHT = 0
CELLS_LIMIT = 0
TRAPS_AMOUNT = 0


@dataclass
class Vector2:
    x: int
    y: int


@dataclass
class GameState:
    cells: list[Vector2]
    traps: list[Vector2]
    safezone: Vector2
    player_pos: Vector2
    is_dead: bool
    score: int


def update(mouse: Vector2, click: bool, reset: bool) -> GameState:
    """Updates the game"""
    pass


def draw(mouse: Vector2):
    """Draws the game"""
    pass


def init():
    """Initializes the game"""
    pass


def close():
    """Closes the window"""
    pass

