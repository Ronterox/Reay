use std::{env, path::PathBuf};

fn main() {
    let root = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap()).join("../..");
    let src = root.join("src");
    let vcpkg = root.join("vcpkg_installed/x64-linux");

    // Compile the C game core into libgame.a and link raylib's static deps after it.
    cc::Build::new()
        .file(src.join("game.c"))
        .include(&src)
        .include(vcpkg.join("include"))
        .compile("game");
    println!(
        "cargo:rustc-link-search=native={}",
        vcpkg.join("lib").display()
    );
    for lib in ["static=raylib", "static=glfw3", "m"] {
        println!("cargo:rustc-link-lib={lib}");
    }
    println!("cargo:rerun-if-changed={}", src.join("game.c").display());
    println!("cargo:rerun-if-changed={}", src.join("game.h").display());

    // Generate Rust declarations from game.h (only what the binding uses).
    bindgen::Builder::default()
        .header(src.join("game.h").to_str().unwrap())
        .clang_arg(format!("-I{}", vcpkg.join("include").display()))
        .allowlist_function("Update|Draw|InitGame|InitGameWindow|IsWindowReady|CloseWindow")
        .allowlist_var("SCREEN_WIDTH|SCREEN_HEIGHT|CELLS_LIMIT|TRAPS_AMOUNT")
        .generate()
        .expect("bindgen failed on game.h")
        .write_to_file(PathBuf::from(env::var("OUT_DIR").unwrap()).join("game.rs"))
        .unwrap();
}
