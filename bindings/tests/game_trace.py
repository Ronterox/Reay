"""Deterministic scripted session, shared by the golden-trace test and its generator."""

STEPS = 400


def run(aigame) -> list[list[int]]:
    aigame.init(False)
    cell_w = aigame.SCREEN_WIDTH // aigame.CELLS_LIMIT
    cell_h = aigame.SCREEN_HEIGHT // aigame.CELLS_LIMIT
    rows = []
    state = aigame.update(aigame.Vector2(0, 0), False, True)
    for step in range(STEPS):
        # Walk a fixed pattern of target cells; click every 7th frame, reset every 150th.
        cx, cy = (step * 3) % 5, (step * 7 // 5) % 5
        mouse = aigame.Vector2(cx * cell_w + cell_w // 2, cy * cell_h + cell_h // 2)
        state = aigame.update(mouse, step % 7 == 0, step % 150 == 149)
        rows.append(
            [state.score, int(state.is_dead), state.player_pos.x, state.player_pos.y, state.safezone.x, state.safezone.y]
            + [c for t in state.traps for c in (t.x, t.y)]
        )
    return rows


if __name__ == "__main__":
    # Regenerate the golden file from whichever aigame is importable (the baseline).
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build" / "c_capi"))
    import aigame

    out = Path(__file__).with_name("golden_trace.json")
    out.write_text(json.dumps(run(aigame)))
    print(f"wrote {out}")
