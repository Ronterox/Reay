//! py.zig: a small comptime layer that turns plain Zig declarations into a
//! CPython extension module (and its .pyi stub).
//!
//!   pub const X: i32 = 1;                  -> int constant
//!   pub const V = struct { x: i32 };       -> class V (members, __init__, __repr__, __reduce__)
//!   pub fn f(a: struct { v: V, b: bool = true }) R  -> def f(v: V, b: bool = True) -> R
//!   pub fn g() void                        -> def g() -> None
//!   pub const __doc__ = .{ .f = "..." };   -> docstrings (Zig doc comments are not reflectable)
//!   comptime { py.exportModule(@This(), "name"); }  -> PyInit_name
//!
//! Supported value types: i32 (other ints convert but are stored as objects),
//! bool (parsed by truthiness, like PyArg "p"), fixed arrays (-> list), structs
//! (-> classes), void (-> None).
const std = @import("std");
const builtin = @import("builtin");

pub const c = @cImport({
    @cDefine("PY_SSIZE_T_CLEAN", {});
    @cInclude("Python.h");
    @cInclude("structmember.h");
});

const PyObject = c.PyObject;
const Error = error{PythonError};

// translate-c cannot handle PyObject_HEAD_INIT / PyVarObject_HEAD_INIT /
// PyModuleDef_HEAD_INIT (brace initialisers) or Py_RETURN_NONE (a statement).
const head_init: PyObject = .{ .ob_refcnt = 1, .ob_type = null };

fn inc(o: *PyObject) *PyObject {
    c.Py_INCREF(o);
    return o;
}

fn none() *PyObject {
    return inc(c.Py_None());
}

fn ok(p: [*c]PyObject) Error!*PyObject {
    const o: ?*PyObject = p;
    return o orelse error.PythonError;
}

fn raise(exc: [*c]PyObject, fmt: [*:0]const u8, args: anytype) Error {
    _ = @call(.auto, c.PyErr_Format, .{ exc, fmt } ++ args);
    return error.PythonError;
}

fn shortName(comptime T: type) [:0]const u8 {
    const full = @typeName(T);
    return full[comptime if (std.mem.lastIndexOfScalar(u8, full, '.')) |i| i + 1 else 0 ..];
}

fn isClass(comptime T: type) bool {
    return switch (@typeInfo(T)) {
        .@"struct" => |s| !s.is_tuple and s.fields.len > 0,
        else => false,
    };
}

// --- value conversion ------------------------------------------------------

pub fn toPython(comptime T: type, v: T) Error!*PyObject {
    switch (@typeInfo(T)) {
        .void => return none(),
        .bool => return ok(c.PyBool_FromLong(@intFromBool(v))),
        .int => return ok(c.PyLong_FromLongLong(v)),
        .array => |a| {
            const list = try ok(c.PyList_New(a.len));
            for (v, 0..) |e, i| {
                const item = toPython(a.child, e) catch |err| {
                    c.Py_DECREF(list);
                    return err;
                };
                _ = c.PyList_SetItem(list, @intCast(i), item); // PyList_SET_ITEM does not translate
            }
            return list;
        },
        .@"struct" => return Class(T).wrap(v),
        else => @compileError("py.zig: cannot convert " ++ @typeName(T) ++ " to Python"),
    }
}

pub fn fromPython(comptime T: type, o: *PyObject) Error!T {
    switch (@typeInfo(T)) {
        .bool => {
            const r = c.PyObject_IsTrue(o);
            return if (r < 0) error.PythonError else r != 0;
        },
        .int => {
            const x = c.PyLong_AsLongLong(o);
            if (x == -1 and c.PyErr_Occurred() != null) return error.PythonError;
            return std.math.cast(T, x) orelse raise(c.PyExc_OverflowError, "value out of range for %s", .{@typeName(T).ptr});
        },
        .array => |a| {
            if (c.PyList_Check(o) == 0 or c.PyList_Size(o) != a.len)
                return raise(c.PyExc_TypeError, "expected a list of %d items", .{@as(c_int, a.len)});
            var out: T = undefined;
            for (&out, 0..) |*e, i| e.* = try fromPython(a.child, c.PyList_GetItem(o, @intCast(i)));
            return out;
        },
        .@"struct" => return Class(T).unwrap(o),
        else => @compileError("py.zig: cannot convert Python to " ++ @typeName(T)),
    }
}

// --- argument parsing (positional + keyword, defaults from field initialisers)

fn Parser(comptime Args: type, comptime fname: [:0]const u8) type {
    return struct {
        const fields = @typeInfo(Args).@"struct".fields;
        const Slots = [fields.len]?*PyObject;

        fn checkCount(n: usize) Error!void {
            if (n > fields.len)
                return raise(c.PyExc_TypeError, "%s() takes at most %d arguments (%zd given)", .{ fname.ptr, @as(c_int, fields.len), @as(c.Py_ssize_t, @intCast(n)) });
        }

        fn keyword(slots: *Slots, key: *PyObject, value: *PyObject) Error!void {
            inline for (fields, 0..) |f, i| {
                if (c.PyUnicode_CompareWithASCIIString(key, f.name.ptr) == 0) {
                    if (slots[i] != null)
                        return raise(c.PyExc_TypeError, "%s() got multiple values for argument '%s'", .{ fname.ptr, f.name.ptr });
                    slots[i] = value;
                    return;
                }
            }
            return raise(c.PyExc_TypeError, "%s() got an unexpected keyword argument '%U'", .{ fname.ptr, key });
        }

        fn finish(slots: *const Slots) Error!Args {
            var out: Args = undefined;
            inline for (fields, 0..) |f, i| {
                @field(out, f.name) = if (slots[i]) |o|
                    try fromPython(f.type, o)
                else
                    f.defaultValue() orelse return raise(c.PyExc_TypeError, "%s() missing required argument '%s' (pos %d)", .{ fname.ptr, f.name.ptr, @as(c_int, i + 1) });
            }
            return out;
        }

        /// tp_init-style (tuple, dict) calling convention.
        fn fromTupleDict(args: *PyObject, kwds: ?*PyObject) Error!Args {
            var slots: Slots = @splat(null);
            const n: usize = @intCast(c.PyTuple_Size(args));
            try checkCount(n);
            // PyTuple_GET_ITEM indexes a translated `[1]` flexible array: bounds-check panic in safe builds.
            for (0..n) |i| slots[i] = c.PyTuple_GetItem(args, @intCast(i));
            if (kwds) |d| {
                var pos: c.Py_ssize_t = 0;
                var k: [*c]PyObject = null;
                var v: [*c]PyObject = null;
                while (c.PyDict_Next(d, &pos, &k, &v) != 0) try keyword(&slots, k, v);
            }
            return finish(&slots);
        }

        /// METH_FASTCALL | METH_KEYWORDS calling convention.
        fn fromVector(args: [*c]const [*c]PyObject, nargs: usize, kwnames: ?*PyObject) Error!Args {
            var slots: Slots = @splat(null);
            try checkCount(nargs);
            for (0..nargs) |i| slots[i] = args[i];
            if (kwnames) |names| {
                for (0..@intCast(c.PyTuple_Size(names))) |i|
                    try keyword(&slots, c.PyTuple_GetItem(names, @intCast(i)), args[nargs + i]);
            }
            return finish(&slots);
        }
    };
}

// --- classes ----------------------------------------------------------------

/// Python storage for T: PyObject header + one C slot per field.
/// i32/bool are stored inline (exposed as T_INT/T_BOOL members); everything else as an owned PyObject*.
fn Slot(comptime T: type) type {
    return if (T == i32 or T == bool) T else ?*PyObject;
}

pub fn Class(comptime T: type) type {
    const fields = @typeInfo(T).@"struct".fields;
    return struct {
        const name = shortName(T);

        pub const Object = blk: {
            var names: [fields.len + 1][]const u8 = undefined;
            var types: [fields.len + 1]type = undefined;
            names[0] = "ob_base"; // PyObject_HEAD does not translate either
            types[0] = PyObject;
            for (fields, 1..) |f, i| {
                names[i] = f.name;
                types[i] = Slot(f.type);
            }
            break :blk @Struct(.@"extern", null, &names, &types, &@splat(.{}));
        };

        var members = blk: {
            var m: [fields.len + 1]c.PyMemberDef = undefined;
            for (fields, 0..) |f, i| m[i] = .{
                .name = f.name.ptr,
                .type = switch (Slot(f.type)) {
                    i32 => c.T_INT,
                    bool => c.T_BOOL,
                    else => c.T_OBJECT_EX,
                },
                .offset = @offsetOf(Object, f.name),
                .flags = 0,
                .doc = null,
            };
            m[fields.len] = std.mem.zeroes(c.PyMemberDef);
            break :blk m;
        };

        var methods = [_]c.PyMethodDef{
            .{ .ml_name = "__reduce__", .ml_meth = &reduce, .ml_flags = c.METH_NOARGS, .ml_doc = "Return state information for pickling" },
            std.mem.zeroes(c.PyMethodDef),
        };

        pub var type_object: c.PyTypeObject = blk: {
            var t = std.mem.zeroes(c.PyTypeObject);
            t.ob_base.ob_base = head_init;
            t.tp_name = @typeName(T); // "<file>.<Decl>", i.e. "aigame.Vector2"
            t.tp_basicsize = @sizeOf(Object);
            t.tp_flags = c.Py_TPFLAGS_DEFAULT;
            t.tp_new = c.PyType_GenericNew;
            t.tp_init = &init;
            t.tp_dealloc = &dealloc;
            t.tp_repr = &repr;
            t.tp_members = &members;
            t.tp_methods = &methods;
            break :blk t;
        };

        fn self(o: [*c]PyObject) *Object {
            return @ptrCast(@alignCast(o));
        }

        fn store(s: *Object, v: T) Error!void {
            inline for (fields) |f| {
                if (Slot(f.type) == f.type) {
                    @field(s, f.name) = @field(v, f.name);
                } else {
                    const old = @field(s, f.name);
                    @field(s, f.name) = try toPython(f.type, @field(v, f.name));
                    c.Py_XDECREF(old);
                }
            }
        }

        pub fn wrap(v: T) Error!*PyObject {
            const o = try ok(c.PyType_GenericAlloc(&type_object, 0));
            store(self(o), v) catch |err| {
                c.Py_DECREF(o);
                return err;
            };
            return o;
        }

        pub fn unwrap(o: *PyObject) Error!T {
            if (c.PyObject_TypeCheck(o, &type_object) == 0)
                return raise(c.PyExc_TypeError, "expected %s, got %.200s", .{ name.ptr, c.Py_TYPE(o).*.tp_name });
            const s = self(o);
            var v: T = undefined;
            inline for (fields) |f| {
                @field(v, f.name) = if (Slot(f.type) == f.type)
                    @field(s, f.name)
                else
                    try fromPython(f.type, @field(s, f.name) orelse
                        return raise(c.PyExc_AttributeError, "%s.%s is not set", .{ name.ptr, f.name.ptr }));
            }
            return v;
        }

        fn fieldTuple(s: *Object) Error!*PyObject {
            const t = try ok(c.PyTuple_New(fields.len));
            inline for (fields, 0..) |f, i| {
                const v = @field(s, f.name);
                const item: *PyObject = if (Slot(f.type) != f.type) (if (v) |o| inc(o) else none()) else toPython(f.type, v) catch |err| {
                    c.Py_DECREF(t);
                    return err;
                };
                _ = c.PyTuple_SetItem(t, i, item);
            }
            return t;
        }

        fn init(o: [*c]PyObject, args: [*c]PyObject, kwds: [*c]PyObject) callconv(.c) c_int {
            const v = Parser(T, name).fromTupleDict(args, kwds) catch return -1;
            store(self(o), v) catch return -1;
            return 0;
        }

        fn dealloc(o: [*c]PyObject) callconv(.c) void {
            inline for (fields) |f| if (Slot(f.type) != f.type) c.Py_XDECREF(@field(self(o), f.name));
            c.Py_TYPE(o).*.tp_free.?(o);
        }

        fn repr(o: [*c]PyObject) callconv(.c) [*c]PyObject {
            const t = fieldTuple(self(o)) catch return null;
            defer c.Py_DECREF(t);
            if (fields.len == 1) return c.PyUnicode_FromFormat("%s(%R)", name.ptr, c.PyTuple_GetItem(t, 0));
            return c.PyUnicode_FromFormat("%s%R", name.ptr, t); // "Vector2" ++ "(1, -2)"
        }

        fn reduce(o: [*c]PyObject, _: [*c]PyObject) callconv(.c) [*c]PyObject {
            const t = fieldTuple(self(o)) catch return null;
            return c.Py_BuildValue("ON", @as(*PyObject, @ptrCast(&type_object)), t);
        }
    };
}

// --- functions ----------------------------------------------------------------

fn pyType(comptime T: type) []const u8 {
    return switch (@typeInfo(T)) {
        .void => "None",
        .bool => "bool",
        .int => "int",
        .array => |a| "list[" ++ pyType(a.child) ++ "]",
        .@"struct" => shortName(T),
        else => @compileError("py.zig: no Python type for " ++ @typeName(T)),
    };
}

fn pyLiteral(comptime v: anytype) []const u8 {
    return switch (@typeInfo(@TypeOf(v))) {
        .bool => if (v) "True" else "False",
        .int, .comptime_int => std.fmt.comptimePrint("{d}", .{v}),
        else => @compileError("py.zig: unsupported default " ++ @typeName(@TypeOf(v))),
    };
}

/// Fields of the single "named arguments" struct a function takes (empty for zero-arg fns).
fn argFields(comptime F: type) []const std.builtin.Type.StructField {
    const params = @typeInfo(F).@"fn".params;
    return switch (params.len) {
        0 => &.{},
        1 => @typeInfo(params[0].type.?).@"struct".fields,
        else => @compileError("py.zig: exported functions take no params or one struct of named arguments"),
    };
}

/// `(a: int, b: bool = True)` when typed, `(a, b=True)` for __text_signature__.
fn signature(comptime fields: []const std.builtin.Type.StructField, comptime typed: bool) []const u8 {
    var s: []const u8 = "";
    for (fields, 0..) |f, i| {
        s = s ++ (if (i > 0) ", " else "") ++ f.name ++ (if (typed) ": " ++ pyType(f.type) else "");
        if (f.defaultValue()) |d| s = s ++ (if (typed) " = " else "=") ++ pyLiteral(d);
    }
    return s;
}

fn docOf(comptime M: type, comptime name: []const u8) ?[]const u8 {
    if (!@hasDecl(M, "__doc__") or !@hasField(@TypeOf(M.__doc__), name)) return null;
    return @field(M.__doc__, name);
}

fn method(comptime M: type, comptime name: [:0]const u8) c.PyMethodDef {
    const f = @field(M, name);
    const F = @TypeOf(f);
    const R = @typeInfo(F).@"fn".return_type.?;
    const fields = argFields(F);
    // Docstring starting with "name(sig)\n--\n\n" gives inspect.signature() real parameter names.
    // comptimePrint guarantees the 0 sentinel that `[]const u8` concatenation does not.
    const doc = std.fmt.comptimePrint("{s}($module{s}{s})\n--\n\n{s}", .{ name, if (fields.len > 0) ", " else "", signature(fields, false), docOf(M, name) orelse "" });
    if (fields.len == 0) {
        const W = struct {
            fn call(_: [*c]PyObject, _: [*c]PyObject) callconv(.c) [*c]PyObject {
                return toPython(R, f()) catch null;
            }
        };
        return .{ .ml_name = name.ptr, .ml_meth = &W.call, .ml_flags = c.METH_NOARGS, .ml_doc = doc.ptr };
    }
    const Args = @typeInfo(F).@"fn".params[0].type.?;
    const W = struct {
        fn call(_: [*c]PyObject, args: [*c]const [*c]PyObject, nargs: c.Py_ssize_t, kwnames: [*c]PyObject) callconv(.c) [*c]PyObject {
            const a = Parser(Args, name).fromVector(args, @intCast(nargs), kwnames) catch return null;
            return toPython(R, f(a)) catch null;
        }
    };
    return .{ .ml_name = name.ptr, .ml_meth = @ptrCast(&W.call), .ml_flags = c.METH_FASTCALL | c.METH_KEYWORDS, .ml_doc = doc.ptr };
}

// --- module -----------------------------------------------------------------

const Kind = enum { skip, constant, class, function };

fn kindOf(comptime M: type, comptime name: []const u8) Kind {
    if (name[0] == '_') return .skip;
    const T = @TypeOf(@field(M, name));
    if (T == type and isClass(@field(M, name))) return .class;
    return switch (@typeInfo(T)) {
        .int, .comptime_int => .constant,
        .@"fn" => .function,
        else => @compileError("py.zig: don't know how to export pub decl '" ++ name ++ "'"),
    };
}

fn Module(comptime M: type, comptime name: [:0]const u8) type {
    const decls = @typeInfo(M).@"struct".decls;
    return struct {
        var methods = blk: {
            var m: []const c.PyMethodDef = &.{};
            for (decls) |d| if (kindOf(M, d.name) == .function) {
                m = m ++ [_]c.PyMethodDef{method(M, d.name)};
            };
            break :blk (m ++ [_]c.PyMethodDef{std.mem.zeroes(c.PyMethodDef)})[0..].*;
        };

        var def: c.PyModuleDef = blk: {
            var d = std.mem.zeroes(c.PyModuleDef);
            d.m_base.ob_base = head_init;
            d.m_name = name.ptr;
            d.m_size = -1;
            d.m_methods = &methods;
            break :blk d;
        };

        fn create() Error!*PyObject {
            inline for (decls) |d| if (comptime kindOf(M, d.name) == .class) {
                if (c.PyType_Ready(&Class(@field(M, d.name)).type_object) < 0) return error.PythonError;
            };
            const m = try ok(c.PyModule_Create(&def));
            errdefer c.Py_DECREF(m);
            inline for (decls) |d| switch (comptime kindOf(M, d.name)) {
                .class => {
                    const t: *PyObject = @ptrCast(&Class(@field(M, d.name)).type_object);
                    c.Py_INCREF(t);
                    if (c.PyModule_AddObject(m, d.name.ptr, t) < 0) {
                        c.Py_DECREF(t);
                        return error.PythonError;
                    }
                },
                .constant => if (c.PyModule_AddIntConstant(m, d.name.ptr, @field(M, d.name)) < 0) return error.PythonError,
                else => {},
            };
            return m;
        }

        fn pyinit() callconv(.c) [*c]PyObject {
            return create() catch null;
        }
    };
}

/// Exports `PyInit_<name>` when building the shared library (skipped for the stub generator exe).
pub fn exportModule(comptime M: type, comptime name: [:0]const u8) void {
    if (builtin.output_mode == .Lib) @export(&Module(M, name).pyinit, .{ .name = "PyInit_" ++ name });
}

/// The module's .pyi stub, generated from the same declarations at comptime.
pub fn stub(comptime M: type) []const u8 {
    comptime {
        @setEvalBranchQuota(100_000);
        var out: []const u8 = "# Generated at comptime by py.zig from " ++ @typeName(M) ++ ".zig. Do not edit.\n";
        const decls = @typeInfo(M).@"struct".decls;
        for (decls) |d| if (kindOf(M, d.name) == .constant) {
            out = out ++ "\n" ++ d.name ++ ": int";
        };
        out = out ++ "\n";
        for (decls) |d| if (kindOf(M, d.name) == .class) {
            const fields = @typeInfo(@field(M, d.name)).@"struct".fields;
            out = out ++ "\n\nclass " ++ d.name ++ ":\n";
            for (fields) |f| out = out ++ "    " ++ f.name ++ ": " ++ pyType(f.type) ++ "\n";
            out = out ++ "    def __init__(self, " ++ signature(fields, true) ++ ") -> None: ...\n";
        };
        for (decls) |d| if (kindOf(M, d.name) == .function) {
            const F = @TypeOf(@field(M, d.name));
            out = out ++ "\n\ndef " ++ d.name ++ "(" ++ signature(argFields(F), true) ++ ") -> " ++ pyType(@typeInfo(F).@"fn".return_type.?) ++ ":";
            out = out ++ if (docOf(M, d.name)) |doc| "\n    \"\"\"" ++ doc ++ "\"\"\"\n" else " ...\n";
        };
        return out;
    }
}
