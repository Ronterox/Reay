#include "main.c"
#include <python3.10/Python.h>

static State state;

static PyObject *update(PyObject *self, PyObject *args) {
	Update(&state);
	return Py_None;
}

static PyObject *draw(PyObject *self, PyObject *args) {
	Draw(&state);
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
	{"update", update, METH_NOARGS, "Updates the game"},
	{"draw", draw, METH_NOARGS, "Draws the game"},
	{"init", init, METH_NOARGS, "Initializes the game"},
	{"close", close_window, METH_NOARGS, "Closes the window"},
	{NULL, NULL, 0, NULL},
};

// Module definition
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "aigame", NULL, -1, methods};

// Module initialization
PyMODINIT_FUNC PyInit_aigame(void) { return PyModule_Create(&module); }
