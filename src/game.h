#pragma once

#include "raylib.h"
#include <sys/types.h>

#define fori(i, n) for (int i = 0; i < n; ++i)
#define forij(i, j, n) fori(i, n) fori(j, n)
#define rng(n) (GetRandomValue(0, n - 1))

#define Vec2(x, y)                                                                                                     \
	(struct Vector2) { x, y }

#define SCREEN_WIDTH 800.
#define SCREEN_HEIGHT 600.
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
	uint score;
} State;

Vector2 GetSafeZone(const Vector2 trapPositions[]);
void Update(State *s, const Vector2 mouse, const bool click, const bool reset);
void Draw(State *s, const Vector2 mouse);
void InitGameWindow(void);
State InitGame(void);
