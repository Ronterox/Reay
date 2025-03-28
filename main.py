import random as rng
import aigame


class Game:
    def __init__(self):
        aigame.init()

    def sample(self) -> tuple[int, int, bool]:
        x, y = rng.randint(0, aigame.SCREEN_WIDTH - 1), rng.randint(0, aigame.SCREEN_HEIGHT - 1)
        click = rng.choice([True, False])
        return x, y, click

    def step(self, action: tuple[int, int, bool]) -> tuple[aigame.GameState, int, bool]:
        self.mouse = aigame.Vector2(action[0], action[1])
        state = aigame.update(self.mouse, action[2], False)
        return state, state.score, state.is_dead

    def reset(self):
        self.mouse = aigame.Vector2(0, 0)
        return aigame.update(self.mouse, False, True), False

    def render(self):
        aigame.draw(self.mouse)

    def close(self):
        aigame.close()


game = Game()
state, done = game.reset()

# rx,ry
# 10t
# 5x5
# x,y
# tx,ty

# T=trap R=Reward
# U=up D=down L=left R=right
# State aware genetic algorithms policy
# state = 'UT LT RF DF UR'
# best[state]
# Swap best[state] with best[state2] for mutation
# Or combinations for multiple chain of actions

for i in range(10):
    state, done = game.reset()
    print(f'Round {i+1}')

    total_reward = 0
    while not done:
        state, reward, done = game.step(game.sample())
        total_reward += reward
        game.render()

    print(f'Total reward: {total_reward}')

game.close()
