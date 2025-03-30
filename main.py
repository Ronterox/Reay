import random as rng
import aigame
import json

from concurrent.futures import ProcessPoolExecutor
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
    def __init__(self, epsilon: float = 1.0) -> None:
        self.epsilon = epsilon
        self.eps_decay = 0.995
        self.eps_min = 0.01

        self.init = False
        self.state: aigame.GameState

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
        assert self.state is not None, 'Game not initialized with reset()'

        sizew = aigame.SCREEN_WIDTH // aigame.CELLS_LIMIT

        direction = self.action_map[action[0]]
        self.mouse = aigame.Vector2(
            (self.state.player_pos.x + direction.x) * sizew,
            (self.state.player_pos.y + direction.y) * sizew,
        )

        game_state = aigame.update(self.mouse, action[1], False)
        state, reward = self.env_model(self.state, game_state, action[0])

        self.state = game_state

        return state, reward, game_state.is_dead

    def env_model(self, old_state: aigame.GameState, new_state: aigame.GameState, action: Direction) -> tuple[State, int]:
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

        player = old_state.player_pos
        safezone = old_state.safezone

        reward = 0

        old_distance = abs(player.x - safezone.x) + abs(player.y - safezone.y)
        new_distance = abs(new_state.player_pos.x - new_state.safezone.x) + \
            abs(new_state.player_pos.y - new_state.safezone.y)

        if new_distance < old_distance:
            reward += 2
        elif new_distance > old_distance:
            reward -= 1

        if old_state.score < new_state.score:
            reward += 5

        if new_state.is_dead:
            reward = -100

        key = ''
        traps = [(t.x, t.y) for t in old_state.traps]
        for act in self.actions:
            direction = self.action_map[act]
            key += f'{act.name[0]}'
            if (player.x + direction.x, player.y + direction.y) in traps:
                key += 'T '
            else:
                key += 'F '

        key += 'W'
        sz, px, py = safezone, player.x, player.y

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
        if not self.init:
            aigame.init()
            self.init = True

        game = aigame.update(self.mouse, False, True)

        self.mouse = aigame.Vector2(0, 0)
        self.state = game

        return self.env_model(self.state, self.state, self.actions[0])[0], False

    def render(self) -> None:
        aigame.draw(self.mouse)

    def close(self) -> None:
        aigame.close()


def none() -> tuple[Direction, float]:
    return rng.choice([Direction.UP, Direction.DOWN,
                       Direction.LEFT, Direction.RIGHT, Direction.NONE]), -float('inf')


def train_agent(game: Game, best: defaultdict, episodes: int, render: bool = False) -> tuple[defaultdict, float]:
    total_reward = 0

    for i in range(episodes):
        state, done = game.reset()
        if render:
            print(f'Round {i+1}')

        round_reward = 0
        frames = 0

        acc_state = State(default=Direction.NONE)
        acc_reward = 0
        acc_name = 'default'
        while not done:
            if frames % 20 == 0:
                if render:
                    print(acc_state[acc_name], acc_reward)

                if rng.random() < game.epsilon:
                    state, reward, done = game.step(game.sample())
                else:
                    state, reward, done = game.step((best[list(state.keys())[0]][0], True))

                acc_name = list(state.keys())[0]
                acc_state = state
                acc_reward = reward
                game.epsilon = max(game.eps_min, game.epsilon * game.eps_decay)
            else:
                state, reward, done = game.step((Direction.NONE, False))
                acc_reward += reward

                if acc_reward > best[acc_name][1]:
                    best[acc_name] = (acc_state[acc_name], acc_reward)

            round_reward += reward

            if render:
                game.render()

            frames += 1

        total_reward += round_reward
        if render:
            print(f'Round reward: {round_reward}')

    game.close()

    fitness = total_reward / episodes
    if render:
        print('=' * 20)
        print(f'Moves learned: {len(best)}')
        print(f"Fitness: {fitness}")

    return best, fitness


def deploy_agents(moves: list[defaultdict], episodes: int) -> list[tuple[defaultdict, float]]:
    with ProcessPoolExecutor() as executor:
        print('=' * 20)
        print(f'Training {len(moves)} agents')
        futures = [executor.submit(train_agent, Game(), m, episodes) for m in moves]
        results = [f.result() for f in futures]

    print('=' * 20)
    print("Agents trained", len(results))
    return results


if __name__ == '__main__':
    elitism = 0.1
    mutation_rate = 0.2

    agents = 50
    episodes = 100
    generations = 10

    children = [defaultdict(none) for _ in range(agents)]

    for i in range(1, generations + 1):
        print('=' * 20)
        print(f"Generation {i}...")
        results = deploy_agents((children * agents)[:agents], episodes)
        bests = sorted(results, key=lambda x: x[1], reverse=True)[:int(elitism * len(results))]

        print(f'Overall Average: {sum([x[1] for x in results]) / len(results)}')

        children = []
        for (mom, mfit), (dad, dfit) in zip(bests[:-1], bests[1:]):
            print(f'Parents: {mfit}, {dfit}')
            print(f'Moves: {len(mom)}, {len(dad)}')
            child = defaultdict(none)
            for key in mom.keys() | dad.keys():
                if key in mom and key in dad:
                    child[key] = dad[key] if rng.random() < mutation_rate else mom[key]
                else:
                    child[key] = mom[key] if key in mom else dad[key]
            children.extend([mom, dad, child])

    d, f = train_agent(Game(epsilon=0.), children[0], episodes, render=True)
    print(d, f)

    with open('best.json', 'w') as f:
        json.dump(d, f)
