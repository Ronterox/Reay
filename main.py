import aigame
import random


class Game:
    def __init__(self):
        aigame.init()
        self.mouse = aigame.Vector2(0, 0)

    def step(self, reset: bool = False) -> tuple[aigame.GameState, int, bool]:
        self.mouse = aigame.Vector2(
            random.randint(0, aigame.SCREEN_WIDTH - 1),
            random.randint(0, aigame.SCREEN_HEIGHT - 1),
        )
        state = aigame.update(self.mouse, random.choice([True, False]), reset)
        return state, state.score, state.is_dead

    def reset(self):
        return self.step(reset=True)

    def render(self):
        aigame.draw(self.mouse)

    def close(self):
        aigame.close()


game = Game()


for i in range(10):
    state, reward, done = game.reset()

    while not done:
        state, reward, done = game.step()
        print(reward)
        game.render()

game.close()
