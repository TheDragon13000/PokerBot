"""Runs a match (or a fixed-stack session) of many hands between a fixed set of bots."""

import heapq
import random
from typing import Dict, List, Optional

from poker.engine import BotFn, GameConfig, play_hand, resolve_hook
from poker.state import HandSummary
from poker.stats import Stats


class _TopK:
    """Bounded top-K tracker for curated replays (biggest wins & losses, seat 0).

    Min-heaps keyed so the *least* interesting candidate sits at the root and gets
    evicted first. The hand index breaks net ties so event lists are never compared.
    """

    def __init__(self, k: int):
        self.k = k
        self.wins: List[tuple] = []    # (net, hand, events) — smallest win at root
        self.losses: List[tuple] = []  # (-net, hand, events) — mildest loss at root

    def offer(self, net: int, hand: int, events: List[dict]) -> None:
        if self.k <= 0:
            return
        if net > 0:
            heapq.heappush(self.wins, (net, hand, events))
            if len(self.wins) > self.k:
                heapq.heappop(self.wins)
        elif net < 0:
            heapq.heappush(self.losses, (-net, hand, events))
            if len(self.losses) > self.k:
                heapq.heappop(self.losses)

    def curated(self) -> List[dict]:
        out: List[dict] = []
        for net, hand, events in sorted(self.wins, reverse=True):
            out.append({"kind": "win", "hand": hand, "net": net, "events": events})
        for neg, hand, events in sorted(self.losses, reverse=True):
            out.append({"kind": "loss", "hand": hand, "net": -neg, "events": events})
        return out


def _notify_hooks(hooks, button: int, n: int, result) -> None:
    if not any(hooks):
        return
    summary = HandSummary(
        button=button,
        num_players=n,
        board=result.board,
        betting_history=result.betting_history,
        net=result.net,
        winners=result.winners,
        showdown_seats=result.showdown_seats,
        revealed=result.revealed,
    )
    for hook in hooks:
        if hook is not None:
            try:
                hook(summary)
            except Exception:
                pass  # a buggy learning hook must not break the match


def run_match(
    bots: Dict[str, BotFn],
    hands: int,
    config: Optional[GameConfig] = None,
    seed: Optional[int] = None,
    log: bool = False,
    capture_events: int = 0,
    curate: int = 0,
) -> Stats:
    """Play `hands` hands between the given bots and return collected Stats.

    Each bot keeps a fixed seat; the dealer button advances by one every hand, so
    over a full rotation each bot plays every position equally. A fresh, seeded deck
    is shuffled per hand for reproducibility. If config.stack is set, every seat is
    refilled to that stack each hand (all-ins and side pots apply within a hand).

    `bots` maps a display name to either a function `act(state) -> action` or a
    stateful bot object (an instance with an `act` method and an optional
    `on_hand_end(summary)` hook). Both styles can share one match.

    Replay capture — two independent modes:
      * `capture_events=N` records the first N hands into `stats.replays`.
      * `curate=K` records every hand and keeps the K biggest wins and K biggest
        losses *for seat 0* (the player) in `stats.curated`, each as a dict
        `{"kind": "win"|"loss", "hand": <index>, "net": <chips>, "events": [...]}`,
        ordered biggest win first, then biggest loss first. Memory stays bounded:
        only the current top-K candidates' event streams are retained.
    """
    if len(bots) < 2:
        raise ValueError("need at least 2 bots")
    config = config or GameConfig()
    rng = random.Random(seed)

    names: List[str] = list(bots.keys())
    seats: List[BotFn] = [bots[nm] for nm in names]
    n = len(seats)

    # Collect learning hooks for stateful bots (functions have none).
    hooks = [resolve_hook(b) for b in seats]

    stats = Stats(names, big_blind=config.big_blind)
    topk = _TopK(curate)

    for h in range(hands):
        button = h % n
        record = h < capture_events or curate > 0
        result = play_hand(seats, button, config, rng=rng, log=log,
                           record_events=record)
        stats.record(result)
        if h < capture_events:
            stats.replays.append(result.events)
        if curate > 0:
            topk.offer(result.net[0], h, result.events)

        _notify_hooks(hooks, button, n, result)

        if log:
            print(f"--- Hand {h} (button=seat {button}) ---")
            print("\n".join(result.log))

    stats.curated = topk.curated()
    return stats


def run_session(
    bots: Dict[str, BotFn],
    stack: int,
    max_hands: int,
    config: Optional[GameConfig] = None,
    seed: Optional[int] = None,
    log: bool = False,
    curate: int = 0,
) -> Stats:
    """A fixed-stack roll for seat 0 (the player): one `stack`, carried hand to hand.

    The player starts with `stack` chips and keeps whatever remains after each hand;
    every other seat refills to `stack` at the start of each hand (the table always
    has opponents with chips). The session ends when the player busts (stack 0) or
    `max_hands` is reached.

    Returns Stats with session fields filled in: `session_stack` (the player's stack
    after each hand — the survival timeline), `session_busted`, and
    `session_final_stack`. Curated replays work as in run_match.
    """
    if len(bots) < 2:
        raise ValueError("need at least 2 bots")
    if stack <= 0:
        raise ValueError("stack must be positive")
    config = config or GameConfig()
    rng = random.Random(seed)

    names: List[str] = list(bots.keys())
    seats: List[BotFn] = [bots[nm] for nm in names]
    n = len(seats)
    hooks = [resolve_hook(b) for b in seats]

    stats = Stats(names, big_blind=config.big_blind)
    topk = _TopK(curate)

    player = stack
    for h in range(max_hands):
        button = h % n
        result = play_hand(seats, button, config, rng=rng, log=log,
                           record_events=curate > 0,
                           stacks=[player] + [stack] * (n - 1))
        stats.record(result)
        player += result.net[0]
        stats.session_stack.append(player)
        if curate > 0:
            topk.offer(result.net[0], h, result.events)
        _notify_hooks(hooks, button, n, result)
        if player <= 0:
            break

    stats.curated = topk.curated()
    stats.session_busted = player <= 0
    stats.session_final_stack = max(player, 0)
    return stats
