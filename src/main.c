#include "raylib.h"
#include "raymath.h"

#define fori(i, n) for (int i = 0; i < n; ++i)

//------------------------------------------------------------------------------------
// Program main entry point
//------------------------------------------------------------------------------------
int main(void) {
	// Initialization
	//--------------------------------------------------------------------------------------
	const int screenWidth = 800;
	const int screenHeight = 600;

	const int limit = 5;
	const int sizew = screenWidth / limit;
	const int sizeh = screenHeight / limit;

	const int mousesize = 10;

	InitWindow(screenWidth, screenHeight, "Raey");

	HideCursor();
	SetTargetFPS(60);

	// TODO: Load resources / Initialize variables at this point

	Vector2 playerPos = {0, 0};
	Vector2 spritePos = {playerPos.x * sizew + sizew / 2., playerPos.y * sizeh + sizeh / 2.};
	Vector2 trapPos = {0, 0};

	//--------------------------------------------------------------------------------------

	// Main game loop
	while (!WindowShouldClose()) // Detect window close button or ESC key
	{
		// Update
		//----------------------------------------------------------------------------------
		// TODO: Update variables / Implement example logic at this point
		//----------------------------------------------------------------------------------

		const Vector2 mouse = {GetMousePosition().x, GetMousePosition().y};
		const Vector2 targetPos = {playerPos.x * sizew + sizew / 2., playerPos.y * sizeh + sizeh / 2.};

		if (spritePos.x != targetPos.x || spritePos.y != targetPos.y) {
			spritePos = Vector2Lerp(spritePos, targetPos, 0.1);
		}

		if (IsMouseButtonPressed(MOUSE_BUTTON_LEFT)) {
			fori(i, limit) {
				fori(j, limit) {
					const Rectangle cell = {sizew * i, sizeh * j, sizew, sizeh};
					if (CheckCollisionCircleRec(mouse, 1, cell)) {
						playerPos = (struct Vector2){i, j};
						break;
					}
				}
			}
		}

		// Draw
		//----------------------------------------------------------------------------------
		BeginDrawing();

		ClearBackground(BLACK);

		// TODO: Draw everything that requires to be drawn at this point:

		fori(i, limit) {
			fori(j, limit) {
				DrawRectangle(sizew * i, sizeh * j, sizew, sizeh, (i + j) % 2 == 0 ? RED : BLUE);
				if (trapPos.x == i && trapPos.y == j) {
					DrawRectangle(sizew * i + sizew * 0.1, sizeh * j + sizeh * 0.1, sizew * 0.8, sizeh * 0.8, ORANGE);
				}
			}
		}

		DrawCircleV(spritePos, sizew - sizeh, YELLOW);
		DrawCircleV(mouse, mousesize, GREEN);

		EndDrawing();
		//----------------------------------------------------------------------------------
	}

	// De-Initialization
	//--------------------------------------------------------------------------------------

	// TODO: Unload all loaded resources at this point

	CloseWindow(); // Close window and OpenGL context
	//--------------------------------------------------------------------------------------

	return 0;
}
