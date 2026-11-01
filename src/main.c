#include "game.h"

int main(void) {
	InitGameWindow();
	State state = InitGame();

	while (!WindowShouldClose()) // Detect window close button or ESC key
	{
		const Vector2 mouse = GetMousePosition();
		Update(&state, mouse, IsMouseButtonPressed(MOUSE_LEFT_BUTTON), IsKeyPressed(KEY_R));
		Draw(&state, mouse);
	}

	CloseWindow(); // Close window and OpenGL context
	return 0;
}
