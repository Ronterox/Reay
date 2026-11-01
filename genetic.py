"""Genetic training of state -> action tables for the aigame trap-dodging game.

Every run writes runs/<timestamp>[-name]/ so it can be inspected afterwards:

    config.json        exact settings of the run
    generations.jsonl  one line per generation: fitness stats, deaths, behaviour
    agents.csv         one row per agent per generation
    policies/          best.json (best generation average so far), last.json
    traces/            gen_XXX.jsonl: every decision of greedy play by the
                       generation's best agent (state, key, action, reward, ...)
    fitness.png        fitness curves
    summary.json       final numbers

Defaults are the best configuration found (see the flag comments in Config).
The original algorithm is still available with:

    --decide-every 5 --update v1 --reward v1 --horizon 1
"""
import argparse
import csv
import json
import os
import random as rng
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import IntEnum
from statistics import mean, median

import matplotlib

matplotlib.use('Agg')  # save plots to the run dir instead of blocking on plt.show()
import matplotlib.pyplot as plt
from rich.progress import track

import aigame

# Traps grow for ~300 frames per wave and only kill once nearly full size.
# Measured: deaths start at phase 56 (frames since the wave's traps appeared).
DEADLY_PHASE = 55
WAVE_FRAMES = 300
REVERSAL_PENALTY = 4  # reward v4: undoing the previous move (left after right, ...)


class Direction(IntEnum):
    UP = 0
    DOWN = 1
    LEFT = 2
    RIGHT = 3
    NONE = 4


OPPOSITE = {Direction.UP: Direction.DOWN, Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT, Direction.RIGHT: Direction.LEFT}
STEP = {Direction.UP: (0, -1), Direction.DOWN: (0, 1), Direction.LEFT: (-1, 0),
        Direction.RIGHT: (1, 0), Direction.NONE: (0, 0)}

Action = tuple[Direction, bool]
State = dict[str, Direction]


@dataclass
class Config:
    agents: int = 24
    episodes: int = 100
    generations: int = 60
    elitism: float = 0.1
    mutation_rate: float = 0.25
    eps_decay: float = 0.995
    eps_min: float = 0.01
    decide_every: int = 10    # frames between decisions; a move takes ~7 frames to register
    state: str = 'v1'         # v1: neighbours + safezone direction; v2: + walls + wave phase
    reward: str = 'v3'        # v1: original; v2: no penalty for standing still, -2 for moving away
                              # v3: v2, but the safezone bonus needs the player's cell to be the safezone
                              # v4: v3, but moving away is free (detours) and reversing the previous
                              #     move costs REVERSAL_PENALTY (no back-and-forth farming)
    update: str = 'v3'        # v1: original per-frame partial sums; v2: whole decision window
                              # v3: v2 windows, but keep a running mean return for every action
    horizon: int = 12         # update v2/v3: credit each decision with the next N windows' rewards
    gamma: float = 0.85       # discount per window for --horizon > 1
    max_waves: int = 20       # cap so a perfect agent cannot run forever
    eval_episodes: int = 10   # greedy (epsilon 0, no learning) episodes per agent after training
    select: str = 'train'     # rank agents by 'train' fitness (original) or greedy 'eval' fitness
    trace_every: int = 10     # write a greedy trace of the generation's best agent every N gens
    trace_episodes: int = 3
    workers: int = 0          # 0 = all cores
    seed: int = 0
    out: str = 'runs'
    name: str = ''


class Game:
    def __init__(self, epsilon: float = 1.0, window: bool = False, cfg: Config | None = None) -> None:
        cfg = cfg or Config()
        self.epsilon = epsilon
        self.window = window  # open a raylib window; training workers run headless
        self.eps_decay = cfg.eps_decay
        self.eps_min = cfg.eps_min
        self.state_version = cfg.state
        self.reward_version = cfg.reward

        self.init = False
        self.state: aigame.GameState
        self.wave = 0   # waves survived this episode
        self.phase = 0  # frames since the current wave's traps appeared
        self._traps: list[tuple[int, int]] | None = None
        self.last_move: Direction | None = None  # last non-NONE direction clicked
        self.reversal = False                    # this step undid the previous move

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

    def _track_wave(self, game_state: aigame.GameState) -> None:
        traps = [(t.x, t.y) for t in game_state.traps]
        if traps != self._traps:
            if self._traps is not None:
                self.wave += 1
            self._traps = traps
            self.phase = 0
        else:
            self.phase += 1

    def step(self, action: Action) -> tuple[State, int, bool]:
        assert len(action) == 2 and action[0] in self.actions, 'Invalid action'
        assert self.state is not None, 'Game not initialized with reset()'

        sizew = aigame.SCREEN_WIDTH // aigame.CELLS_LIMIT
        sizeh = aigame.SCREEN_HEIGHT // aigame.CELLS_LIMIT

        # Click the centre of the target cell (screen y grows downward)
        direction = self.action_map[action[0]]
        self.mouse = aigame.Vector2(
            (self.state.player_pos.x + direction.x) * sizew + sizew // 2,
            (self.state.player_pos.y + direction.y) * sizeh + sizeh // 2,
        )

        self.reversal = False
        if action[1] and action[0] != Direction.NONE:
            self.reversal = self.last_move == OPPOSITE[action[0]]
            self.last_move = action[0]

        game_state = aigame.update(self.mouse, action[1], False)
        state, reward = self.env_model(self.state, game_state, action[0])

        self.state = game_state
        self._track_wave(game_state)

        return state, reward, game_state.is_dead

    def dist(self, a: aigame.Vector2, b: aigame.Vector2) -> tuple[int, int]:
        return abs(a.x - b.x), abs(a.y - b.y)

    def reward_v1(self, old_state: aigame.GameState, new_state: aigame.GameState) -> int:
        reward = 0

        old_distx, old_disty = self.dist(old_state.player_pos, old_state.safezone)
        new_distx, new_disty = self.dist(new_state.player_pos, new_state.safezone)

        if new_distx < old_distx or new_disty < old_disty:
            reward += 2
        else:
            reward -= 1

        sz_dist_x, sz_dist_y = self.dist(old_state.safezone, new_state.safezone)
        if old_state.score < new_state.score:
            reward += 5
        elif (sz_dist_x != 0 or sz_dist_y != 0):
            reward -= 120

        if new_state.is_dead:
            reward = -120
        return reward

    def reward_v2(self, old_state: aigame.GameState, new_state: aigame.GameState, away_penalty: int = 2) -> int:
        """Like v1, but standing still costs nothing and moving away costs -away_penalty."""
        reward = 0

        old_d = sum(self.dist(old_state.player_pos, old_state.safezone))
        new_d = sum(self.dist(new_state.player_pos, new_state.safezone))
        if new_state.safezone.x == old_state.safezone.x and new_state.safezone.y == old_state.safezone.y:
            if new_d < old_d:
                reward += 2
            elif new_d > old_d:
                reward -= away_penalty

        sz_dist_x, sz_dist_y = self.dist(old_state.safezone, new_state.safezone)
        if old_state.score < new_state.score:
            reward += 5
        elif (sz_dist_x != 0 or sz_dist_y != 0):
            reward -= 120

        if new_state.is_dead:
            reward = -120
        return reward

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

        state v2 adds B=border (moving there is a no-op) and the wave phase:
        state = 'UB DT LF RB NT WXRD P1'
        P0: traps harmless, P1: traps about to turn deadly, P2: traps deadly
        """

        if self.reward_version in ('v3', 'v4'):
            reward = self.reward_v2(old_state, new_state, away_penalty=0 if self.reward_version == 'v4' else 2)
            if self.reward_version == 'v4' and self.reversal:
                reward -= REVERSAL_PENALTY
            on_safezone = (new_state.player_pos.x == old_state.safezone.x
                           and new_state.player_pos.y == old_state.safezone.y)
            if old_state.score < new_state.score and not on_safezone and not new_state.is_dead:
                reward -= 5  # only overlapping the safezone while passing through: no bonus
        elif self.reward_version == 'v2':
            reward = self.reward_v2(old_state, new_state)
        else:
            reward = self.reward_v1(old_state, new_state)

        player = old_state.player_pos
        safezone = old_state.safezone
        n = aigame.CELLS_LIMIT

        key = ''
        traps = [(t.x, t.y) for t in old_state.traps]
        for act in self.actions:
            direction = self.action_map[act]
            cell = (player.x + direction.x, player.y + direction.y)
            key += f'{act.name[0]}'
            if self.state_version == 'v2' and not (0 <= cell[0] < n and 0 <= cell[1] < n):
                key += 'B '
            elif cell in traps:
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
        else:
            key += 'X' + ('R' if px < sz.x else 'L') + ('U' if py > sz.y else 'D')

        if self.state_version == 'v2':
            bucket = 0 if self.phase < DEADLY_PHASE - 25 else 1 if self.phase < DEADLY_PHASE else 2
            key += f' P{bucket}'

        return {key: action}, reward

    def reset(self) -> tuple[State, bool]:
        if not self.init:
            aigame.init(self.window)
            self.init = True

        game = aigame.update(self.mouse, False, True)

        self.mouse = aigame.Vector2(0, 0)
        self.state = game
        self.wave, self.phase, self._traps = 0, 0, None
        self.last_move, self.reversal = None, False
        self._track_wave(game)

        return self.env_model(self.state, self.state, self.actions[0])[0], False

    def render(self) -> None:
        aigame.draw(self.mouse)

    def close(self) -> None:
        aigame.close()


def none() -> tuple[Direction, float]:
    return rng.choice([Direction.UP, Direction.DOWN,
                       Direction.LEFT, Direction.RIGHT, Direction.NONE]), -float('inf')


def choose(entry, explore: bool = False) -> Direction:
    """Action of a table entry: (action, value) for update v1/v2, {action: [mean, n]} for v3.
    explore: while learning, v3 first tries every action once in each state."""
    if isinstance(entry, dict):
        if explore:
            untried = [a for a in Direction if a not in entry]
            if untried:
                return rng.choice(untried)
        return max(entry, key=lambda a: entry[a][0])
    return entry[0]


def commit_mean(best: defaultdict, name: str, action: Direction, ret: float, min_alpha: float = 0.05) -> None:
    entry = best[name]
    if not isinstance(entry, dict):
        entry = {}
    m, n = entry.get(action, (0., 0))
    n += 1
    m += (ret - m) * max(1 / n, min_alpha)  # running mean that keeps adapting as the policy improves
    entry[action] = [m, n]
    best[name] = entry


def commit(best: defaultdict, name: str, action: Direction, reward: float) -> None:
    b_move, b_reward = best[name]
    if reward > b_reward or action == b_move and reward != b_reward:
        best[name] = (action, reward)


def commit_returns(best: defaultdict, windows: list, horizon: int, gamma: float, commit_fn=commit) -> None:
    """Credit each decision with its discounted n-step return, so a death is also
    blamed on the decisions that walked into (or failed to leave) a trap earlier."""
    rewards = [r for _, _, r in windows]
    for t, (name, action, _) in enumerate(windows):
        ret = sum(gamma ** k * rewards[t + k] for k in range(min(horizon, len(rewards) - t)))
        commit_fn(best, name, action, ret)


def play_episode(game: Game, best: defaultdict, cfg: Config, learn: bool = True,
                 trace: list | None = None, render: bool = False) -> dict:
    """One episode. learn=False plays greedily (epsilon 0) without touching the table."""
    state, done = game.reset()
    frames = decisions = nones = leaves = 0
    blocked = detours = blocked_waits = into_trap = 0
    reached: set[int] = set()  # waves in which the player stood on the safezone
    n = aigame.CELLS_LIMIT
    capped = False

    acc_action = Direction.NONE
    acc_reward = 0
    acc_name = 'default'
    row = None
    windows: list = []  # (key, action, window reward) when --horizon > 1
    windowed = cfg.update in ('v2', 'v3')
    commit_fn = commit_mean if cfg.update == 'v3' else commit
    while not done:
        if cfg.max_waves and game.wave >= cfg.max_waves:
            capped = True
            break

        if frames % cfg.decide_every == 0:
            if learn and windowed and frames > 0:
                if cfg.horizon > 1:
                    windows.append((acc_name, acc_action, acc_reward))
                else:
                    commit_fn(best, acc_name, acc_action, acc_reward)
            if row is not None:
                row['window_reward'] = acc_reward

            s = game.state
            at_safezone = s.player_pos.x == s.safezone.x and s.player_pos.y == s.safezone.y
            key = next(iter(state))
            if learn and rng.random() < game.epsilon:
                action = game.sample()
            elif learn:
                action = (choose(best[key], explore=True), True)
            else:
                action = (choose(best[key] if key in best else none()), True)

            if trace is not None:
                row = {'frame': frames, 'wave': game.wave, 'phase': game.phase,
                       'player': [s.player_pos.x, s.player_pos.y], 'safezone': [s.safezone.x, s.safezone.y],
                       'traps': sorted({(t.x, t.y) for t in s.traps}), 'key': key,
                       'known': key in best, 'action': action[0].name, 'score': s.score}
                trace.append(row)

            state, reward, done = game.step(action)

            decisions += 1
            nones += action[0] == Direction.NONE
            leaves += at_safezone and action[0] != Direction.NONE
            if at_safezone:
                reached.add(game.wave)
            elif game.phase >= DEADLY_PHASE:
                # blocked: traps are deadly and every step toward the safezone is a trap
                p, sz = (s.player_pos.x, s.player_pos.y), (s.safezone.x, s.safezone.y)
                traps = {(t.x, t.y) for t in s.traps}
                toward = [(p[0] + dx, p[1] + dy) for dx, dy in (STEP[d] for d in OPPOSITE)
                          if abs(p[0] + dx - sz[0]) + abs(p[1] + dy - sz[1]) < abs(p[0] - sz[0]) + abs(p[1] - sz[1])]
                if all(c in traps for c in toward):
                    blocked += 1
                    dx, dy = STEP[action[0]]
                    target = (p[0] + dx, p[1] + dy)
                    if action[0] == Direction.NONE or not (0 <= target[0] < n and 0 <= target[1] < n):
                        blocked_waits += 1
                    elif target in traps:
                        into_trap += 1
                    else:
                        detours += 1

            acc_name = next(iter(state))
            acc_action = state[acc_name]
            acc_reward = reward
            if learn:
                game.epsilon = max(game.eps_min, game.epsilon * game.eps_decay)
        else:
            state, reward, done = game.step((Direction.NONE, False))
            acc_reward += reward

            if learn and cfg.update == 'v1':
                commit(best, acc_name, acc_action, acc_reward)

        if render:
            game.render()

        frames += 1

    if learn and windowed:  # last window, includes the death penalty
        if cfg.horizon > 1:
            windows.append((acc_name, acc_action, acc_reward))
            commit_returns(best, windows, cfg.horizon, cfg.gamma, commit_fn)
        else:
            commit_fn(best, acc_name, acc_action, acc_reward)
    if row is not None:
        row['window_reward'] = acc_reward
    if trace is not None:
        trace.append({'end': True, 'frame': frames, 'wave': game.wave, 'phase': game.phase,
                      'died': done, 'capped': capped, 'score': game.state.score,
                      'player': [game.state.player_pos.x, game.state.player_pos.y]})

    return {'score': game.state.score, 'frames': frames, 'waves': game.wave, 'died': done,
            'death_phase': game.phase if done else None, 'capped': capped,
            'decisions': decisions, 'nones': nones, 'leaves': leaves,
            'reached': len(reached), 'waves_played': game.wave + (0 if capped else 1),
            'blocked': blocked, 'detours': detours, 'blocked_waits': blocked_waits, 'into_trap': into_trap}


EMPTY_EPISODE = {'score': 0, 'waves': 0, 'died': False, 'death_phase': None, 'capped': False,
                 'decisions': 0, 'nones': 0, 'leaves': 0, 'reached': 0, 'waves_played': 0,
                 'blocked': 0, 'detours': 0, 'blocked_waits': 0, 'into_trap': 0}


def summarize(episodes: list[dict]) -> dict:
    if not episodes:
        return {}
    scores = [e['score'] for e in episodes]
    deaths = [e['death_phase'] for e in episodes if e['died']]
    decisions = sum(e['decisions'] for e in episodes) or 1
    blocked = sum(e['blocked'] for e in episodes)
    return {
        'fitness': mean(scores),
        'median': median(scores),
        'max': max(scores),
        'waves': mean(e['waves'] for e in episodes),
        'capped': sum(e['capped'] for e in episodes),
        'deaths': len(deaths),
        # when in a wave deaths happen: right as traps arm, or later while walking into them
        'death_at_arming': sum(DEADLY_PHASE <= p <= DEADLY_PHASE + 5 for p in deaths),
        'death_later': sum(p > DEADLY_PHASE + 5 for p in deaths),
        'none_ratio': sum(e['nones'] for e in episodes) / decisions,
        'leaves_per_episode': sum(e['leaves'] for e in episodes) / len(episodes),
        # share of waves where the player got onto the safezone
        'reach_rate': sum(e['reached'] for e in episodes) / (sum(e['waves_played'] for e in episodes) or 1),
        # when every step toward the safezone is a deadly trap: go around, wait, or walk in
        'blocked_decisions': blocked,
        'blocked_detour_rate': sum(e['detours'] for e in episodes) / (blocked or 1),
        'blocked_wait_rate': sum(e['blocked_waits'] for e in episodes) / (blocked or 1),
        'blocked_into_trap_rate': sum(e['into_trap'] for e in episodes) / (blocked or 1),
    }


def train_agent(game: Game, best: defaultdict, cfg: Config, seed: int) -> tuple[defaultdict, dict, dict]:
    rng.seed(seed)
    train = [play_episode(game, best, cfg, learn=True) for _ in range(cfg.episodes)]
    greedy = [play_episode(game, best, cfg, learn=False) for _ in range(cfg.eval_episodes)]
    game.close()
    return best, summarize(train), summarize(greedy)


def fitness_of(result: tuple, cfg: Config) -> float:
    _, train, greedy = result
    return greedy['fitness'] if cfg.select == 'eval' and greedy else train['fitness']


def deploy_agents(moves: list[defaultdict], cfg: Config, gen: int) -> list[tuple[defaultdict, dict, dict]]:
    with ProcessPoolExecutor(max_workers=cfg.workers or None) as executor:
        futures = [executor.submit(train_agent, Game(cfg=cfg), m, cfg, cfg.seed * 1_000_003 + gen * 1000 + i)
                   for i, m in enumerate(moves)]
        return [f.result() for f in futures]


# ---------------------------------------------------------------- run output

def table_to_json(best: dict) -> dict:
    """{key: [action, value]} for update v1/v2, {key: {action: [mean, n]}} for v3."""
    out = {}
    for k, v in sorted(best.items()):
        if isinstance(v, dict):
            out[k] = {a.name: [round(m, 2), n] for a, (m, n) in sorted(v.items(), key=lambda x: -x[1][0])}
        else:
            out[k] = [v[0].name, v[1] if v[1] != -float('inf') else None]
    return out


def table_from_json(data: dict) -> defaultdict:
    table = defaultdict(none)
    for k, v in data.items():
        if isinstance(v, dict):
            table[k] = {Direction[a]: [m, n] for a, (m, n) in v.items()}
        else:
            table[k] = (Direction[v[0]], -float('inf') if v[1] is None else v[1])
    return table


def write_trace(path: str, best: defaultdict, cfg: Config, seed: int) -> dict:
    saved = rng.getstate()  # keep the crossover RNG stream independent of tracing
    rng.seed(seed)
    game = Game(epsilon=0., cfg=cfg)
    trace: list = []
    stats = []
    for ep in range(cfg.trace_episodes):
        start = len(trace)
        stats.append(play_episode(game, best, cfg, learn=False, trace=trace))
        for row in trace[start:]:
            row['episode'] = ep
    with open(path, 'w') as f:
        for row in trace:
            f.write(json.dumps(row) + '\n')
    rng.setstate(saved)
    return summarize(stats)


def demo(best: defaultdict, cfg: Config, episodes: int, window: bool = True) -> list[dict]:
    """Play greedily (no exploration, no learning) in a raylib window at 60 FPS."""
    game = Game(epsilon=0., window=window, cfg=cfg)
    results = []
    for ep in range(1, episodes + 1):
        r = play_episode(game, best, cfg, learn=False, render=True)
        end = f"died at phase {r['death_phase']}" if r['died'] else 'hit the wave cap'
        print(f"episode {ep}: score {r['score']:>9,} | waves survived {r['waves']:>2} | {end} | "
              f"stood still {r['nones'] / max(r['decisions'], 1):.0%}")
        results.append(r)
    game.close()
    if results:
        print(f"average score {mean(r['score'] for r in results):,.0f} over {len(results)} episodes")
    return results


def plot(path: str, history: list[dict]) -> None:
    gens = [h['gen'] for h in history]
    plt.figure(figsize=(9, 5))
    plt.plot(gens, [h['train_avg'] for h in history], label='train fitness, population avg')
    plt.plot(gens, [h['train_best'] for h in history], label='train fitness, best agent')
    if history and history[0].get('greedy_best') is not None:
        plt.plot(gens, [h['greedy_best'] for h in history], label='greedy fitness, best agent')
        plt.plot(gens, [h['greedy_avg'] for h in history], label='greedy fitness, population avg')
    plt.xlabel('generation')
    plt.ylabel('mean score per episode')
    plt.legend()
    plt.grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()


def parse_args() -> tuple[Config, argparse.Namespace]:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for field, default in asdict(Config()).items():
        flag = '--' + field.replace('_', '-')
        p.add_argument(flag, type=type(default), default=default)
    p.add_argument('--demo', action='store_true', help='after training, play the final best policy in a window')
    p.add_argument('--load', help='skip training: play a saved policy JSON in a window, '
                                  "using its run's config.json for --state/--decide-every")
    p.add_argument('--demo-episodes', type=int, default=5, help='episodes to play with --demo/--load')
    args = p.parse_args()
    cfg = Config(**{f: getattr(args, f) for f in asdict(Config())})
    if cfg.generations < 1 or cfg.agents < 1 or cfg.decide_every < 1:
        p.error('--generations, --agents and --decide-every must be >= 1')
    return cfg, args


def main() -> None:
    cfg, args = parse_args()

    if args.load:
        with open(args.load) as f:
            best = table_from_json(json.load(f))
        run_config = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.load))), 'config.json')
        if os.path.exists(run_config):  # play with the state encoding and cadence it was trained on
            with open(run_config) as f:
                trained = json.load(f)
            cfg.state, cfg.decide_every = trained['state'], trained['decide_every']
        print(f'Playing {args.load} ({len(best)} states, --state {cfg.state}, '
              f'--decide-every {cfg.decide_every}, max {cfg.max_waves or "unlimited"} waves)')
        demo(best, cfg, args.demo_episodes)
        return

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    run_dir = os.path.join(cfg.out, stamp + (f'-{cfg.name}' if cfg.name else ''))
    if os.path.exists(run_dir):  # two runs started in the same second
        run_dir += f'-{os.getpid()}'
    os.makedirs(os.path.join(run_dir, 'policies'))
    os.makedirs(os.path.join(run_dir, 'traces'))
    with open(os.path.join(run_dir, 'config.json'), 'w') as f:
        json.dump(asdict(cfg), f, indent=2)
    print(f'Writing run to {run_dir}')

    agent_fields = ['gen', 'agent', 'rank', 'parent_of_next', 'table_size'] + \
        [f'train_{k}' for k in summarize([EMPTY_EPISODE])] + [f'greedy_{k}' for k in summarize([EMPTY_EPISODE])]
    agents_csv = open(os.path.join(run_dir, 'agents.csv'), 'w', newline='')
    agents_writer = csv.DictWriter(agents_csv, fieldnames=agent_fields)
    agents_writer.writeheader()
    gens_log = open(os.path.join(run_dir, 'generations.jsonl'), 'w')

    n_parents = min(max(2, int(cfg.elitism * cfg.agents)), cfg.agents)
    children = [defaultdict(none) for _ in range(cfg.agents)]
    history: list[dict] = []
    best_avg = -float('inf')
    t0 = time.time()

    for gen in track(range(1, cfg.generations + 1), description='Training'):
        results = deploy_agents((children * cfg.agents)[:cfg.agents], cfg, gen)
        order = sorted(range(len(results)), key=lambda i: fitness_of(results[i], cfg), reverse=True)
        bests = [(results[i][0], fitness_of(results[i], cfg)) for i in order[:n_parents]]

        for rank, i in enumerate(order):
            table, train, greedy = results[i]
            agents_writer.writerow({'gen': gen, 'agent': i, 'rank': rank, 'parent_of_next': rank < n_parents,
                                    'table_size': len(table),
                                    **{f'train_{k}': v for k, v in train.items()},
                                    **{f'greedy_{k}': v for k, v in greedy.items()}})
        agents_csv.flush()

        trains = [r[1] for r in results]
        greedys = [r[2] for r in results if r[2]]
        top_table, top_train, top_greedy = results[order[0]]
        entry = {
            'gen': gen,
            'elapsed_s': round(time.time() - t0, 1),
            'train_avg': mean(t['fitness'] for t in trains),
            'train_best': max(t['fitness'] for t in trains),
            'train_min': min(t['fitness'] for t in trains),
            'greedy_avg': mean(g['fitness'] for g in greedys) if greedys else None,
            'greedy_best': max(g['fitness'] for g in greedys) if greedys else None,
            'waves_avg': mean(t['waves'] for t in trains),
            'death_at_arming': sum(t['death_at_arming'] for t in trains),
            'death_later': sum(t['death_later'] for t in trains),
            'deaths': sum(t['deaths'] for t in trains),
            'none_ratio': mean(t['none_ratio'] for t in trains),
            'leaves_per_episode': mean(t['leaves_per_episode'] for t in trains),
            'reach_rate': mean(t['reach_rate'] for t in trains),
            'greedy_reach_rate': mean(g['reach_rate'] for g in greedys) if greedys else None,
            'greedy_blocked_detour_rate': (sum(g['blocked_detour_rate'] * g['blocked_decisions'] for g in greedys)
                                           / (sum(g['blocked_decisions'] for g in greedys) or 1)) if greedys else None,
            'table_size_avg': mean(len(r[0]) for r in results),
            'top_agent': {'train': top_train, 'greedy': top_greedy, 'table_size': len(top_table)},
        }

        if gen % cfg.trace_every == 0 or gen == cfg.generations or gen == 1:
            entry['trace'] = write_trace(os.path.join(run_dir, 'traces', f'gen_{gen:03d}.jsonl'),
                                         top_table, cfg, seed=gen)

        history.append(entry)
        gens_log.write(json.dumps(entry) + '\n')
        gens_log.flush()

        print(f"gen {gen:>3} | train avg {entry['train_avg']:>9,.0f} best {entry['train_best']:>9,.0f} | "
              f"greedy best {entry['greedy_best'] or 0:>9,.0f} | waves {entry['waves_avg']:.2f} | "
              f"none {entry['none_ratio']:.0%} | reach {entry['reach_rate']:.0%} | {entry['elapsed_s']:.0f}s")

        if entry['train_avg'] >= best_avg:
            best_avg = entry['train_avg']
            with open(os.path.join(run_dir, 'policies', 'best.json'), 'w') as f:
                json.dump(table_to_json(bests[0][0]), f, indent=0)

        children = [] if len(bests) > 1 else [bests[0][0]]
        for (mom, mfit), (dad, dfit) in zip(bests[:-1], bests[1:]):
            child = defaultdict(none)
            for key in mom.keys() | dad.keys():
                if key in mom and key in dad:
                    child[key] = dad[key] if rng.random() < cfg.mutation_rate else mom[key]
                else:
                    child[key] = mom[key] if key in mom else dad[key]
            children.extend([mom, dad, child])

    agents_csv.close()
    gens_log.close()

    with open(os.path.join(run_dir, 'policies', 'last.json'), 'w') as f:
        json.dump(table_to_json(children[0]), f, indent=0)
    plot(os.path.join(run_dir, 'fitness.png'), history)
    peak = max(history, key=lambda h: h['train_avg'])
    summary = {'run_dir': run_dir, 'elapsed_s': round(time.time() - t0, 1),
               'peak_train_avg': peak['train_avg'], 'peak_gen': peak['gen'],
               'final_train_avg': history[-1]['train_avg'],
               'best_greedy': max((h['greedy_best'] or 0) for h in history)}
    with open(os.path.join(run_dir, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))

    if args.demo:
        demo(children[0], cfg, args.demo_episodes)


if __name__ == '__main__':
    main()
