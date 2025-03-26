#include "main.c"
#include <python3.10/Python.h>
#include <python3.10/structmember.h>

typedef struct {
	PyObject_HEAD;
	int x;
	int y;
} Vector2Object;

typedef struct {
	PyObject_HEAD;
	PyObject *cells;	  // List of Vector2
	PyObject *traps;	  // List of Vector2
	PyObject *safezone;	  // Vector2
	PyObject *player_pos; // Vector2
	bool is_dead;
	int score;
} GameStateObject;

static State state;

static PyMemberDef GameState_members[] = {
	{"cells", T_OBJECT, offsetof(GameStateObject, cells), 0, "List of cell positions"},
	{"traps", T_OBJECT_EX, offsetof(GameStateObject, traps), 0, "List of trap positions"},
	{"safezone", T_OBJECT_EX, offsetof(GameStateObject, safezone), 0, "Safe zone position"},
	{"player_pos", T_OBJECT_EX, offsetof(GameStateObject, player_pos), 0, "Player position"},
	{"is_dead", T_INT, offsetof(GameStateObject, is_dead), 0, "Is player dead"},
	{"score", T_INT, offsetof(GameStateObject, score), 0, "Current score"},
	{NULL},
};

static PyTypeObject GameStateType = {
	PyVarObject_HEAD_INIT(NULL, 0).tp_name = "aigame.GameState",
	.tp_basicsize = sizeof(GameStateObject),
	.tp_itemsize = 0,
	.tp_flags = Py_TPFLAGS_DEFAULT,
	.tp_new = PyType_GenericNew,
	.tp_members = GameState_members,
};

static PyObject *Vector2_Str(Vector2Object *self) { return PyUnicode_FromFormat("Vector2(%d, %d)", self->x, self->y); }

static int Vector2_Init(Vector2Object *self, PyObject *args, PyObject *kwds) {
	static char *kwlist[] = {"x", "y", NULL};
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "ii", kwlist, &self->x, &self->y)) return -1; // Initialization failed
	return 0;
}

static PyTypeObject Vector2Type = {
	PyVarObject_HEAD_INIT(NULL, 0).tp_name = "aigame.Vector2",
	.tp_basicsize = sizeof(Vector2Object),
	.tp_itemsize = 0,
	.tp_flags = Py_TPFLAGS_DEFAULT,
	.tp_new = PyType_GenericNew,
	.tp_init = (initproc)Vector2_Init,
	.tp_str = (reprfunc)Vector2_Str,
	.tp_repr = (reprfunc)Vector2_Str,
};

static PyObject *Vector2_New(int x, int y) {
	Vector2Object *obj = (Vector2Object *)Vector2Type.tp_new(&Vector2Type, NULL, NULL);
	obj->x = x;
	obj->y = y;
	return (PyObject *)obj;
}

static int Convert_Vector2(PyObject *obj, void *ptr) {
	if (!PyObject_TypeCheck(obj, &Vector2Type)) {
		PyErr_SetString(PyExc_TypeError, "Expected a Vector2 object");
		return 0;
	}
	Vector2Object *src = (Vector2Object *)obj;
	Vector2Object *dest = (Vector2Object *)ptr;
	dest->x = src->x;
	dest->y = src->y;
	return 1;
}

static PyObject *update(PyObject *self, PyObject *args) {
	Vector2Object mouse;
	bool click, reset;

	if (!PyArg_ParseTuple(args, "O&ii", Convert_Vector2, &mouse, &click, &reset)) return NULL;

	Update(&state, Vec2(mouse.x, mouse.y), click, reset);

	GameStateObject *obj = (GameStateObject *)GameStateType.tp_new(&GameStateType, NULL, NULL);

	obj->cells = PyList_New(CELLS_LIMIT * CELLS_LIMIT);
	forij(i, j, CELLS_LIMIT) { PyList_SetItem(obj->cells, i * CELLS_LIMIT + j, Vector2_New(i, j)); }

	obj->traps = PyList_New(TRAPS_AMOUNT);
	fori(i, TRAPS_AMOUNT) {
		PyList_SetItem(obj->traps, i, Vector2_New(state.trapPositions[i].x, state.trapPositions[i].y));
	}

	obj->safezone = Vector2_New(state.safeZone.x, state.safeZone.y);
	obj->player_pos = Vector2_New(state.playerPos.x, state.playerPos.y);
	obj->is_dead = state.isDead;
	obj->score = state.score;

	return (PyObject *)obj;
}

static PyObject *draw(PyObject *self, PyObject *args) {
	Vector2Object mouse;

	if (!PyArg_ParseTuple(args, "O!", &Vector2Type, &mouse)) return NULL;

	Draw(&state, Vec2(mouse.x, mouse.y));

	return Py_None;
}

static PyObject *init(PyObject *self, PyObject *args) {
	state = InitGame();
	return Py_None;
}

static PyObject *close_window(PyObject *self, PyObject *args) {
	CloseWindow();
	return Py_None;
}

// Method definition
static PyMethodDef methods[] = {
	{"update", update, METH_VARARGS, "Updates the game"},
	{"draw", draw, METH_VARARGS, "Draws the game"},
	{"init", init, METH_NOARGS, "Initializes the game"},
	{"close", close_window, METH_NOARGS, "Closes the window"},
	{NULL, NULL, 0, NULL},
};

// Module definition
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "aigame", NULL, -1, methods};

// Module initialization
PyMODINIT_FUNC PyInit_aigame(void) {
	if (PyType_Ready(&Vector2Type) < 0) return NULL;
	if (PyType_Ready(&GameStateType) < 0) return NULL;

	PyObject *m = PyModule_Create(&module);

	Py_INCREF(&Vector2Type);
	PyModule_AddObject(m, "Vector2", (PyObject *)&Vector2Type);

	Py_INCREF(&GameStateType);
	PyModule_AddObject(m, "GameState", (PyObject *)&GameStateType);

	PyModule_AddIntConstant(m, "SCREEN_WIDTH", SCREEN_WIDTH);
	PyModule_AddIntConstant(m, "SCREEN_HEIGHT", SCREEN_HEIGHT);
	PyModule_AddIntConstant(m, "CELLS_LIMIT", CELLS_LIMIT);
	PyModule_AddIntConstant(m, "TRAPS_AMOUNT", TRAPS_AMOUNT);

	return m;
}
