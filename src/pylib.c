#include "main.c"
#include <python3.10/Python.h>

// The C function we want to call from Python
static PyObject *run(PyObject *self, PyObject *args) {
	run_game();
	return Py_None;
}

// Method definition
static PyMethodDef methods[] = {{"run", run, METH_NOARGS, "Run the game"}, {NULL, NULL, 0, NULL}};

// Module definition
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "aigame", NULL, -1, methods};

// Module initialization
PyMODINIT_FUNC PyInit_aigame(void) { return PyModule_Create(&module); }
