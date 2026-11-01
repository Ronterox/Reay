//! The `aigame` Python module. Every pub decl below is exported by py.zig;
//! the .pyi stub is generated from these same declarations.
const py = @import("py.zig");
const g = @cImport(@cInclude("game.h"));

comptime {
    py.exportModule(@This(), "aigame");
}

pub const SCREEN_WIDTH: i32 = @intFromFloat(g.SCREEN_WIDTH);
pub const SCREEN_HEIGHT: i32 = @intFromFloat(g.SCREEN_HEIGHT);
pub const CELLS_LIMIT: i32 = @intFromFloat(g.CELLS_LIMIT);
pub const TRAPS_AMOUNT: i32 = g.TRAPS_AMOUNT;

pub const Vector2 = struct { x: i32, y: i32 };

pub const GameState = struct {
    cells: [CELLS_LIMIT * CELLS_LIMIT]Vector2,
    traps: [TRAPS_AMOUNT]Vector2,
    safezone: Vector2,
    player_pos: Vector2,
    is_dead: bool,
    score: i32,
};

pub const __doc__ = .{
    .update = "Updates the game",
    .draw = "Draws the game",
    .init = "Initializes the game, opening a window only if render",
    .close = "Closes the window",
};

var state: g.State = undefined;

pub fn update(a: struct { mouse: Vector2, click: bool, reset: bool }) GameState {
    g.Update(&state, toC(a.mouse), a.click, a.reset);
    var s: GameState = .{
        .cells = undefined,
        .traps = undefined,
        .safezone = fromC(state.safeZone, 1, 1),
        .player_pos = fromC(state.spritePos, g.SCREEN_WIDTH / g.CELLS_LIMIT, g.SCREEN_HEIGHT / g.CELLS_LIMIT), // pixels -> cell
        .is_dead = state.isDead,
        .score = @bitCast(state.score),
    };
    const n: usize = CELLS_LIMIT;
    for (&s.cells, 0..) |*cell, k| cell.* = .{ .x = @intCast(k / n), .y = @intCast(k % n) };
    for (&s.traps, state.trapPositions) |*t, p| t.* = fromC(p, 1, 1);
    return s;
}

pub fn draw(a: struct { mouse: Vector2 }) void {
    if (g.IsWindowReady()) g.Draw(&state, toC(a.mouse)); // no-op when headless
}

pub fn init(a: struct { render: bool = true }) void {
    if (a.render and !g.IsWindowReady()) g.InitGameWindow();
    state = g.InitGame();
}

pub fn close() void {
    if (g.IsWindowReady()) g.CloseWindow();
}

fn toC(v: Vector2) g.Vector2 {
    return .{ .x = @floatFromInt(v.x), .y = @floatFromInt(v.y) };
}

fn fromC(v: g.Vector2, w: f64, h: f64) Vector2 {
    return .{ .x = @intFromFloat(@as(f64, v.x) / w), .y = @intFromFloat(@as(f64, v.y) / h) };
}
