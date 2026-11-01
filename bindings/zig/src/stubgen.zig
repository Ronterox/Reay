//! Build-time helper: prints the comptime-generated aigame.pyi.
const std = @import("std");

pub fn main(init: std.process.Init) !void {
    try std.Io.File.stdout().writeStreamingAll(init.io, comptime @import("py.zig").stub(@import("aigame.zig")));
}
