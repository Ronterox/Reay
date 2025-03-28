import random as rng
import aigame

from collections import defaultdict
from enum import IntEnum


class Direction(IntEnum):
    UP = 0
    DOWN = 1
    LEFT = 2
    RIGHT = 3
    NONE = 4


Action = tuple[Direction, bool]
State = dict[str, Direction]


class Game:
    def __init__(self) -> None:
        aigame.init()
        self.player = None
        self.score = 0

        self.mouse = aigame.Vector2(0, 0)
        self.actions = [Direction.UP, Direction.DOWN,
                        Direction.LEFT, Direction.RIGHT, Direction.NONE]
        self.action_map = {
            Direction.UP: aigame.Vector2(0, -1),
            Direction.DOWN: aigame.Vector2(0, 1),
            Direction.LEFT: aigame.Vector2(-1, 0),
            Direction.RIGHT: aigame.Vector2(1, 0),
            Direction.NONE: aigame.Vector2(0, 0),
        }

    def sample(self) -> Action:
        return rng.choice(self.actions), True

    def step(self, action: Action) -> tuple[State, int, bool]:
        assert len(action) == 2 and action[0] in self.actions, 'Invalid action'
        assert self.player is not None, 'Game not initialized with reset()'

        sizew = aigame.SCREEN_WIDTH // aigame.CELLS_LIMIT

        direction = self.action_map[action[0]]
        self.mouse = aigame.Vector2(
            (self.player.x + direction.x) * sizew,
            (self.player.y + direction.y) * sizew,
        )

        player = self.player
        score = self.score

        game_state = aigame.update(self.mouse, action[1], False)

        self.player = game_state.player_pos
        self.score = game_state.score

        state, reward = self.env_model(game_state, player, self.score > score, action[0])
        return state, reward, game_state.is_dead

    # state ->
    # rx,ry
    # 10t
    # 5x5
    # x,y
    # tx,ty
    def env_model(self, state: aigame.GameState, player: aigame.Vector2, safe: bool, action: Direction) -> tuple[State, int]:
        assert action in self.actions, 'Invalid action'
        assert len(self.actions) == 5, 'Action space must be 5'

        """
        F=free T=trap W=Reward
        U=up D=down L=left R=right X=Diagonal
        State aware genetic algorithms policy
        state = 'UT DT LF RF NT WXRU'
        best[state] = 'UP'
        Swap best[state] with best[state2] for mutation
        Or combinations for multiple chain of actions
        """

        reward = 0
        if state.is_dead:
            reward = -10
        elif safe:
            reward = 1

        key = ''
        traps = [(t.x, t.y) for t in state.traps]
        for action in self.actions:
            direction = self.action_map[action]
            key += f'{action.name[0]}'
            if (player.x + direction.x, player.y + direction.y) in traps:
                key += 'T '
            else:
                key += 'F '

        key += 'W'
        sz, px, py = state.safezone, player.x, player.y

        if px == sz.x and py == sz.y:
            key += 'N'
        elif px == sz.x:
            key += 'U' if py > sz.y else 'D'
        elif py == sz.y:
            key += 'L' if px > sz.x else 'R'
        elif px < sz.x:
            key += 'XRU' if py < sz.y else 'XRD'
        elif px > sz.x:
            key += 'XLU' if py < sz.y else 'XRD'

        return {key: action}, reward

    def reset(self) -> tuple[State, bool]:
        game = aigame.update(self.mouse, False, True)
        self.mouse = aigame.Vector2(0, 0)
        self.player = game.player_pos
        self.score = 0
        return self.env_model(game, self.player, False, self.actions[0])[0], False

    def render(self) -> None:
        aigame.draw(self.mouse)

    def close(self) -> None:
        aigame.close()


game = Game()

epsilon = 1.
eps_decay = 0.995
eps_min = 0.01

episodes = 100
total_reward = 0


def none() -> tuple[Direction, int]:
    return Direction.NONE, 0


best = defaultdict(none)

for i in range(episodes):
    state, done = game.reset()
    print(f'Round {i+1}')

    round_reward = 0
    frames = 0
    while not done:
        if frames % 4 == 0:
            name = list(state.keys())[0]

            if rng.random() < epsilon:
                state, reward, done = game.step(game.sample())
            else:
                state, reward, done = game.step((best[name][0], True))

            if reward > best[name][1]:
                best[name] = (state[name], reward)

            round_reward += reward
            epsilon = max(eps_min, epsilon * eps_decay)
        else:
            state, reward, done = game.step((Direction.NONE, False))

        # game.render()
        frames += 1

    total_reward += round_reward
    print(f'Round reward: {round_reward}')

print(f'Moves learned: {len(best)}')
print(f"Fitness: {total_reward / episodes}")

game.close()
