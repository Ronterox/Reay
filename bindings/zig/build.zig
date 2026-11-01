const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    const py_include = b.option([]const u8, "python-include", "Python.h directory") orelse "/usr/include/python3.10";
    const vcpkg = b.path("../../vcpkg_installed/x64-linux");

    // Shared library: aigame.zig + py.zig + the untouched C game core + static raylib/glfw.
    const mod = b.createModule(.{
        .root_source_file = b.path("src/aigame.zig"),
        .target = target,
        .optimize = optimize,
        .link_libc = true,
        .pic = true,
    });
    mod.addIncludePath(.{ .cwd_relative = py_include });
    mod.addIncludePath(b.path("../../src"));
    mod.addIncludePath(vcpkg.path(b, "include"));
    // Defensive: clang contracts a*b+c into FMA on native targets, gcc -O2 on generic x86-64 does not.
    // (The golden trace happens to match without it, but other traces might not.)
    mod.addCSourceFile(.{ .file = b.path("../../src/game.c"), .flags = &.{"-ffp-contract=off"} });
    mod.addObjectFile(vcpkg.path(b, "lib/libraylib.a"));
    mod.addObjectFile(vcpkg.path(b, "lib/libglfw3.a"));
    mod.linkSystemLibrary("m", .{});

    const lib = b.addLibrary(.{ .linkage = .dynamic, .name = "aigame", .root_module = mod });
    lib.linker_allow_shlib_undefined = true; // Py* symbols come from the interpreter
    b.getInstallStep().dependOn(&b.addInstallFile(lib.getEmittedBin(), "aigame.so").step);

    // aigame.pyi: a host exe prints the stub py.zig computed at comptime from aigame.zig.
    const gen_mod = b.createModule(.{
        .root_source_file = b.path("src/stubgen.zig"),
        .target = b.graph.host,
        .link_libc = true,
    });
    gen_mod.addIncludePath(.{ .cwd_relative = py_include });
    gen_mod.addIncludePath(b.path("../../src"));
    gen_mod.addIncludePath(vcpkg.path(b, "include"));
    const gen = b.addExecutable(.{ .name = "stubgen", .root_module = gen_mod });
    const pyi = b.addRunArtifact(gen).captureStdOut(.{});
    b.getInstallStep().dependOn(&b.addInstallFile(pyi, "aigame.pyi").step);
}
