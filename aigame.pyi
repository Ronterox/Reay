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

class Vector2:
    x: int
    y: int


class GameState:
    cells: list[Vector2]
    traps: list[Vector2]
    safezone: Vector2
    player_pos: Vector2
    score: int


def update() -> GameState:
    """Updates the game"""
    pass


def draw():
    """Draws the game"""
    pass


def init():
    """Initializes the game"""
    pass


def close():
    """Closes the window"""
    pass

