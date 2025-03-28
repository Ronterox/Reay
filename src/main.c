#include "raylib.h"
#include "raymath.h"

#define fori(i, n) for (int i = 0; i < n; ++i)
#define forij(i, j, n) fori(i, n) fori(j, n)
#define rng(n) (GetRandomValue(0, n - 1))

#define Vec2(x, y)                                                                                                     \
	(struct Vector2) { x, y }

#define SCREEN_WIDTH 800
#define SCREEN_HEIGHT 600
#define CELLS_LIMIT 5.

#define SIZEW SCREEN_WIDTH / CELLS_LIMIT
#define SIZEH SCREEN_HEIGHT / CELLS_LIMIT
#define SPRITE_SIZE SIZEW - SIZEH

#define TRAPS_AMOUNT 10
#define MOUSESIZE 10

typedef struct State {
	Vector2 playerPos;
	Vector2 spritePos;
	bool isDead;

	Vector2 trapPositions[TRAPS_AMOUNT];
	Vector2 trapSize;
	Vector2 safeZone;
	int score;
} State;

Vector2 GetSafeZone(const int limit, const int trapsAmount, const Vector2 trapPositions[]) {
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

void Update(State *s, const Vector2 mouse, const bool click, const bool reset) {
	const Rectangle safeZoneRect = {SIZEW * s->safeZone.x, SIZEH * s->safeZone.y, SIZEW, SIZEH};
	const Vector2 targetPos = {s->playerPos.x * SIZEW + SIZEW / 2., s->playerPos.y * SIZEH + SIZEH / 2.};
	const Vector2 trapTargetSize = {SIZEW, SIZEH};

	const float trapSizeDistance = Vector2Distance(s->trapSize, trapTargetSize);

	if (Vector2Distance(s->spritePos, targetPos) > 1) {
		s->spritePos = Vector2Lerp(s->spritePos, targetPos, 0.1);
	}

	if (!s->isDead && CheckCollisionCircleRec(s->spritePos, SPRITE_SIZE, safeZoneRect)) {
		s->score += 100;
	}

	if (trapSizeDistance > 0.1) {
		if (!s->isDead && trapSizeDistance < 50.) {
			fori(i, TRAPS_AMOUNT) {
				const Rectangle cell = {SIZEW * s->trapPositions[i].x, SIZEH * s->trapPositions[i].y, SIZEW, SIZEH};
				if (CheckCollisionCircleRec(s->spritePos, SPRITE_SIZE, cell)) {
					s->isDead = true;
					break;
				}
			}
		}
		s->trapSize = Vector2Lerp(s->trapSize, trapTargetSize, 0.025);
	} else {
		s->trapSize = Vec2(0, 0);
		fori(i, TRAPS_AMOUNT) { s->trapPositions[i] = Vec2(rng(CELLS_LIMIT), rng(CELLS_LIMIT)); }
		s->safeZone = GetSafeZone(CELLS_LIMIT, TRAPS_AMOUNT, s->trapPositions);
	}

	if (click) {
		forij(i, j, CELLS_LIMIT) {
			const Rectangle cell = {SIZEW * i, SIZEH * j, SIZEW, SIZEH};
			if (CheckCollisionCircleRec(mouse, 1, cell)) {
				s->playerPos = Vec2(i, j);
				break;
			}
		}
	}

	if (reset) {
		s->isDead = false;
		s->playerPos = Vec2(0, 0);
		s->spritePos = Vec2(0, 0);
		s->trapSize = Vec2(0, 0);
		s->safeZone = GetSafeZone(CELLS_LIMIT, TRAPS_AMOUNT, s->trapPositions);
		s->score = 0;

		fori(i, TRAPS_AMOUNT) { s->trapPositions[i] = Vec2(rng(CELLS_LIMIT), rng(CELLS_LIMIT)); }
	}
}

void Draw(State *s, const Vector2 mouse) {
	const Rectangle safeZoneRect = {SIZEW * s->safeZone.x, SIZEH * s->safeZone.y, SIZEW, SIZEH};

	BeginDrawing();
	ClearBackground(BLACK);

	forij(i, j, CELLS_LIMIT) {
		DrawRectangle(SIZEW * i, SIZEH * j, SIZEW, SIZEH, (i + j) % 2 == 0 ? RED : BLUE);
		fori(k, TRAPS_AMOUNT) {
			const Vector2 trapPos = s->trapPositions[k];
			if (trapPos.x == i && trapPos.y == j) {
				DrawRectangle(SIZEW * i, SIZEH * j, s->trapSize.x, s->trapSize.y, ORANGE);
				break;
			}
		}
	}

	DrawRectangleRec(safeZoneRect, GREEN);

	if (!s->isDead) {
		DrawCircleV(s->spritePos, SPRITE_SIZE, YELLOW);
	} else {
		DrawText("You died", SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, 24, WHITE);
	}

	DrawCircleV(mouse, MOUSESIZE, WHITE);
	DrawText(TextFormat("Score: %d", s->score), 10, 10, 24, WHITE);

	EndDrawing();
}

State InitGame(void) {
	SetTraceLogLevel(LOG_ERROR);
	InitWindow(SCREEN_WIDTH, SCREEN_HEIGHT, "Raey");

	HideCursor();
	SetTargetFPS(60);
	SetRandomSeed(2500);

	State state = {
		.playerPos = {0, 0},
		.spritePos = {SIZEW / 2., SIZEH / 2.},
		.isDead = false,

		.trapPositions = {{0}},
		.trapSize = {0, 0},
		.safeZone = {0, 0},
		.score = 0,
	};

	fori(i, TRAPS_AMOUNT) { state.trapPositions[i] = Vec2(rng(CELLS_LIMIT), rng(CELLS_LIMIT)); }
	state.safeZone = GetSafeZone(CELLS_LIMIT, TRAPS_AMOUNT, state.trapPositions);

	return state;
}

int main(void) {
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
