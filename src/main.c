#include "raylib.h"
#include "raymath.h"

#define fori(i, n) for (int i = 0; i < n; ++i)
#define forij(i, j, n) fori(i, n) fori(j, n)
#define rng(n) (GetRandomValue(0, n - 1))

#define Vec2(x, y)                                                                                                     \
	(struct Vector2) { x, y }

Vector2 GetSafeZone(int limit, int trapsAmount, Vector2 trapPositions[]) {
	bool isFree;
	Vector2 safeZone;

	do {
		isFree = true;
		safeZone = Vec2(rng(limit), rng(limit));

		fori(k, trapsAmount) {
			const Vector2 trapPos = trapPositions[k];
			if (trapPos.x == safeZone.x && trapPos.y == safeZone.y) {
				isFree = false;
				break;
			}
		}
	} while (!isFree);

	return safeZone;
}

void run_game() {
	// Initialization
	//--------------------------------------------------------------------------------------
	SetTraceLogLevel(LOG_ERROR);

	const int screenWidth = 800;
	const int screenHeight = 600;

	const int limit = 5;
	const int sizew = screenWidth / limit;
	const int sizeh = screenHeight / limit;
	const int spriteSize = sizew - sizeh;

	const Vector2 trapTargetSize = {sizew, sizeh};
	const int mousesize = 10;
	const int trapsAmount = 10;

	InitWindow(screenWidth, screenHeight, "Raey");

	HideCursor();
	SetTargetFPS(60);
	SetRandomSeed(2500);

	Vector2 playerPos = {0, 0};
	Vector2 spritePos = {playerPos.x * sizew + sizew / 2., playerPos.y * sizeh + sizeh / 2.};

	bool isDead = false;

	Vector2 trapPositions[trapsAmount];
	Vector2 trapSize = {0, 0};
	fori(i, trapsAmount) { trapPositions[i] = Vec2(rng(limit), rng(limit)); }

	Vector2 safeZone = GetSafeZone(limit, trapsAmount, trapPositions);
	int score = 0;

	//--------------------------------------------------------------------------------------

	// Main game loop
	while (!WindowShouldClose()) // Detect window close button or ESC key
	{
		// Update
		//----------------------------------------------------------------------------------

		const Vector2 mouse = {GetMousePosition().x, GetMousePosition().y};
		const Vector2 targetPos = {playerPos.x * sizew + sizew / 2., playerPos.y * sizeh + sizeh / 2.};
		const float trapSizeDistance = Vector2Distance(trapSize, trapTargetSize);

		const Rectangle safeZoneRect = {sizew * safeZone.x, sizeh * safeZone.y, sizew, sizeh};

		if (Vector2Distance(spritePos, targetPos) > 1) {
			spritePos = Vector2Lerp(spritePos, targetPos, 0.1);
		}

		if (!isDead && CheckCollisionCircleRec(spritePos, spriteSize, safeZoneRect)) {
			score += 100;
		}

		if (trapSizeDistance > 0.1) {
			if (!isDead && trapSizeDistance < 50.) {
				fori(i, trapsAmount) {
					const Rectangle cell = {sizew * trapPositions[i].x, sizeh * trapPositions[i].y, sizew, sizeh};
					if (CheckCollisionCircleRec(spritePos, spriteSize, cell)) {
						isDead = true;
						break;
					}
				}
			}
			trapSize = Vector2Lerp(trapSize, trapTargetSize, 0.025);
		} else {
			trapSize = Vec2(0, 0);
			fori(i, trapsAmount) { trapPositions[i] = Vec2(rng(limit), rng(limit)); }
			safeZone = GetSafeZone(limit, trapsAmount, trapPositions);
		}

		if (IsMouseButtonPressed(MOUSE_BUTTON_LEFT)) {
			forij(i, j, limit) {
				const Rectangle cell = {sizew * i, sizeh * j, sizew, sizeh};
				if (CheckCollisionCircleRec(mouse, 1, cell)) {
					playerPos = Vec2(i, j);
					break;
				}
			}
		}

		if (IsKeyPressed(KEY_R)) {
			isDead = false;
			playerPos = Vec2(0, 0);
			trapSize = Vec2(0, 0);
			safeZone = GetSafeZone(limit, trapsAmount, trapPositions);
			score = 0;
		}

		// Draw
		//----------------------------------------------------------------------------------
		BeginDrawing();
		ClearBackground(BLACK);

		forij(i, j, limit) {
			DrawRectangle(sizew * i, sizeh * j, sizew, sizeh, (i + j) % 2 == 0 ? RED : BLUE);
			fori(k, trapsAmount) {
				const Vector2 trapPos = trapPositions[k];
				if (trapPos.x == i && trapPos.y == j) {
					DrawRectangle(sizew * i, sizeh * j, trapSize.x, trapSize.y, ORANGE);
					break;
				}
			}
		}

		DrawRectangleRec(safeZoneRect, GREEN);

		if (!isDead) {
			DrawCircleV(spritePos, spriteSize, YELLOW);
		} else {
			DrawText("You died", screenWidth / 2, screenHeight / 2, 24, WHITE);
		}

		DrawCircleV(mouse, mousesize, WHITE);
		DrawText(TextFormat("Score: %d", score), 10, 10, 24, WHITE);

		EndDrawing();
		//----------------------------------------------------------------------------------
	}

	// De-Initialization
	//--------------------------------------------------------------------------------------

	CloseWindow(); // Close window and OpenGL context

	//--------------------------------------------------------------------------------------
}

int main(void) {
	run_game();
	return 0;
}
