#[allow(
    non_upper_case_globals,
    non_camel_case_types,
    non_snake_case,
    dead_code
)]
mod ffi {
    include!(concat!(env!("OUT_DIR"), "/game.rs"));
}

/// Python bindings for the raylib trap-dodging game.
#[pyo3::pymodule]
mod aigame {
    use super::ffi;
    use pyo3::prelude::*;
    use std::sync::Mutex;

    // The C side keeps one global `static State`; here it lives behind a Mutex.
    static STATE: Mutex<ffi::State> = Mutex::new(unsafe { std::mem::zeroed() });

    #[pymodule_export]
    const SCREEN_WIDTH: i32 = ffi::SCREEN_WIDTH as i32;
    #[pymodule_export]
    const SCREEN_HEIGHT: i32 = ffi::SCREEN_HEIGHT as i32;
    #[pymodule_export]
    const CELLS_LIMIT: i32 = ffi::CELLS_LIMIT as i32;
    #[pymodule_export]
    const TRAPS_AMOUNT: i32 = ffi::TRAPS_AMOUNT as i32;

    #[pyclass(get_all, set_all)]
    struct Vector2 {
        x: i32,
        y: i32,
    }

    #[pymethods]
    impl Vector2 {
        #[new]
        fn new(x: i32, y: i32) -> Self {
            Self { x, y }
        }

        fn __repr__(&self) -> String {
            format!("Vector2({}, {})", self.x, self.y)
        }

        fn __getnewargs__(&self) -> (i32, i32) {
            (self.x, self.y)
        }
    }

    impl Vector2 {
        fn to_c(&self) -> ffi::Vector2 {
            ffi::Vector2 {
                x: self.x as f32,
                y: self.y as f32,
            }
        }
    }

    #[pyclass(get_all, set_all)]
    struct GameState {
        cells: Vec<Py<Vector2>>,
        traps: Vec<Py<Vector2>>,
        safezone: Py<Vector2>,
        player_pos: Py<Vector2>,
        is_dead: bool,
        score: i32,
    }

    /// Updates the game
    // click/reset take any object and use its truthiness, like the C API's "p" format.
    #[pyfunction]
    #[pyo3(signature = (mouse, click: "bool", reset: "bool"))]
    fn update(
        py: Python<'_>,
        mouse: PyRef<'_, Vector2>,
        click: &Bound<'_, PyAny>,
        reset: &Bound<'_, PyAny>,
    ) -> PyResult<GameState> {
        let (click, reset) = (click.is_truthy()?, reset.is_truthy()?);
        let s = {
            let mut state = STATE.lock().unwrap();
            unsafe { ffi::Update(&mut *state, mouse.to_c(), click, reset) };
            *state
        };
        let vec = |x, y| Py::new(py, Vector2 { x, y });
        let n = CELLS_LIMIT;
        Ok(GameState {
            cells: (0..n * n)
                .map(|k| vec(k / n, k % n))
                .collect::<PyResult<_>>()?,
            traps: s
                .trapPositions
                .iter()
                .map(|t| vec(t.x as i32, t.y as i32))
                .collect::<PyResult<_>>()?,
            safezone: vec(s.safeZone.x as i32, s.safeZone.y as i32)?,
            player_pos: vec(
                (s.spritePos.x as f64 / (ffi::SCREEN_WIDTH / ffi::CELLS_LIMIT)) as i32,
                (s.spritePos.y as f64 / (ffi::SCREEN_HEIGHT / ffi::CELLS_LIMIT)) as i32,
            )?,
            is_dead: s.isDead,
            score: s.score as i32,
        })
    }

    /// Draws the game (no-op when no window is open)
    #[pyfunction]
    fn draw(mouse: PyRef<'_, Vector2>) {
        if unsafe { ffi::IsWindowReady() } {
            unsafe { ffi::Draw(&mut *STATE.lock().unwrap(), mouse.to_c()) };
        }
    }

    /// Initializes the game, opening a window only if render
    #[pyfunction]
    #[pyo3(signature = (render = true))]
    fn init(render: bool) {
        unsafe {
            if render && !ffi::IsWindowReady() {
                ffi::InitGameWindow();
            }
            *STATE.lock().unwrap() = ffi::InitGame();
        }
    }

    /// Closes the window
    #[pyfunction]
    fn close() {
        unsafe {
            if ffi::IsWindowReady() {
                ffi::CloseWindow();
            }
        }
    }
}
