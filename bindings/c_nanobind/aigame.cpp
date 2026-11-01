#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

extern "C" {
#include "game.h"
}

namespace nb = nanobind;

// raylib's Vector2 is {float, float}; the Python-facing one is int.
struct Vec {
	int x, y;
};

struct GameState {
	std::vector<Vec> cells, traps;
	Vec safezone, player_pos;
	bool is_dead;
	int score;
};

static State state;

NB_MODULE(aigame, m) {
	nb::class_<Vec>(m, "Vector2")
		.def(nb::init<int, int>(), nb::arg("x"), nb::arg("y"))
		.def_rw("x", &Vec::x)
		.def_rw("y", &Vec::y)
		.def("__repr__", [](const Vec &v) { return "Vector2(" + std::to_string(v.x) + ", " + std::to_string(v.y) + ")"; })
		.def("__getstate__", [](const Vec &v) { return std::make_tuple(v.x, v.y); })
		.def("__setstate__", [](Vec &v, const std::tuple<int, int> &t) { new (&v) Vec{std::get<0>(t), std::get<1>(t)}; });

	nb::class_<GameState>(m, "GameState")
		.def_rw("cells", &GameState::cells)
		.def_rw("traps", &GameState::traps)
		.def_rw("safezone", &GameState::safezone)
		.def_rw("player_pos", &GameState::player_pos)
		.def_rw("is_dead", &GameState::is_dead)
		.def_rw("score", &GameState::score);

	m.def(
		"update",
		[](const Vec &mouse, nb::handle click, nb::handle reset) { // bool caster is strict: ints rejected
			Update(&state, Vector2{(float)mouse.x, (float)mouse.y}, PyObject_IsTrue(click.ptr()), PyObject_IsTrue(reset.ptr()));

			GameState g;
			forij(i, j, CELLS_LIMIT) g.cells.push_back({i, j});
			fori(i, TRAPS_AMOUNT) g.traps.push_back({(int)state.trapPositions[i].x, (int)state.trapPositions[i].y});
			g.safezone = {(int)state.safeZone.x, (int)state.safeZone.y};
			g.player_pos = {(int)(state.spritePos.x / (SCREEN_WIDTH / CELLS_LIMIT)),
							(int)(state.spritePos.y / (SCREEN_HEIGHT / CELLS_LIMIT))};
			g.is_dead = state.isDead;
			g.score = state.score;
			return g;
		},
		nb::arg("mouse"), nb::arg("click"), nb::arg("reset"), "Updates the game");

	m.def("draw", [](const Vec &mouse) {
		if (IsWindowReady()) Draw(&state, Vector2{(float)mouse.x, (float)mouse.y});
	}, nb::arg("mouse"), "Draws the game");

	m.def("init", [](bool render) {
		if (render && !IsWindowReady()) InitGameWindow();
		state = InitGame();
	}, nb::arg("render") = true, "Initializes the game, opening a window only if render");

	m.def("close", [] { if (IsWindowReady()) CloseWindow(); }, "Closes the window");

	m.attr("SCREEN_WIDTH") = (int)SCREEN_WIDTH;
	m.attr("SCREEN_HEIGHT") = (int)SCREEN_HEIGHT;
	m.attr("CELLS_LIMIT") = (int)CELLS_LIMIT;
	m.attr("TRAPS_AMOUNT") = TRAPS_AMOUNT;
}
