"""Behavioural contract every `aigame` binding must satisfy.

The contract is whatever the hand-written CPython C-API module (c_capi) does,
since that is what genetic.py was written against.
"""

import json
import pickle
from pathlib import Path

import game_trace
import pytest

# --- module constants ------------------------------------------------------


@pytest.mark.parametrize(
    "name,value", [("SCREEN_WIDTH", 800), ("SCREEN_HEIGHT", 600), ("CELLS_LIMIT", 5), ("TRAPS_AMOUNT", 10)]
)
def test_constants_are_ints(aigame, name, value):
    got = getattr(aigame, name)
    assert type(got) is int
    assert got == value


# --- Vector2 ---------------------------------------------------------------


def test_vector2_positional_and_keyword(aigame):
    a = aigame.Vector2(1, 2)
    b = aigame.Vector2(x=3, y=4)
    assert (a.x, a.y, b.x, b.y) == (1, 2, 3, 4)
    assert type(a.x) is int


def test_vector2_is_mutable(aigame):
    v = aigame.Vector2(0, 0)
    v.x, v.y = -7, 9
    assert (v.x, v.y) == (-7, 9)


def test_vector2_repr_and_str(aigame):
    v = aigame.Vector2(1, -2)
    assert repr(v) == "Vector2(1, -2)"
    assert str(v) == "Vector2(1, -2)"


@pytest.mark.parametrize("args", [("a", 1), (1.5, 2), (1,), (1, 2, 3)])
def test_vector2_rejects_bad_args(aigame, args):
    with pytest.raises(TypeError):
        aigame.Vector2(*args)


def test_vector2_pickles(aigame):
    # genetic.py ships Vector2s across a ProcessPoolExecutor.
    v = pickle.loads(pickle.dumps(aigame.Vector2(3, -4)))
    assert type(v) is aigame.Vector2
    assert (v.x, v.y) == (3, -4)


def test_types_are_named_under_module(aigame):
    assert aigame.Vector2.__name__ == "Vector2"
    assert aigame.GameState.__name__ == "GameState"


# --- update / GameState ----------------------------------------------------


def test_update_returns_typed_gamestate(aigame):
    s = aigame.update(aigame.Vector2(0, 0), False, True)
    assert isinstance(s, aigame.GameState)
    assert type(s.cells) is list and len(s.cells) == 25
    assert all(type(c) is aigame.Vector2 for c in s.cells)
    assert [(c.x, c.y) for c in s.cells] == [(i, j) for i in range(5) for j in range(5)]
    assert type(s.traps) is list and len(s.traps) == 10
    assert all(type(t) is aigame.Vector2 for t in s.traps)
    assert type(s.safezone) is aigame.Vector2
    assert type(s.player_pos) is aigame.Vector2
    assert type(s.is_dead) is bool
    assert type(s.score) is int


def test_update_rejects_non_vector2_mouse(aigame):
    with pytest.raises(TypeError):
        aigame.update((0, 0), False, False)


def test_update_requires_three_args(aigame):
    with pytest.raises(TypeError):
        aigame.update(aigame.Vector2(0, 0), False)


def test_update_accepts_truthy_flags(aigame):
    # The C-API baseline parses click/reset with "p" (truthiness), so ints work.
    s = aigame.update(aigame.Vector2(0, 0), 0, 1)
    assert s.score == 0 and s.is_dead is False


def test_each_update_returns_fresh_objects(aigame):
    m = aigame.Vector2(0, 0)
    a = aigame.update(m, False, False)
    b = aigame.update(m, False, False)
    assert a is not b and a.safezone is not b.safezone


# --- draw / init / close (headless) ----------------------------------------


def test_draw_headless_is_noop(aigame):
    assert aigame.draw(aigame.Vector2(10, 10)) is None


def test_draw_rejects_non_vector2(aigame):
    with pytest.raises(TypeError):
        aigame.draw(None)


def test_init_and_close_headless(aigame):
    assert aigame.init(False) is None
    assert aigame.close() is None


# --- behavioural equivalence -----------------------------------------------


def test_golden_trace(aigame):
    expected = json.loads(Path(__file__).with_name("golden_trace.json").read_text())
    got = game_trace.run(aigame)
    assert len(got) == len(expected)
    for step, (g, e) in enumerate(zip(got, expected)):
        assert g == e, f"diverged at step {step}"
