"""Plays a single hand of Texas Hold'em — Limit (the default) or No-Limit.

Stacks are optional. With no stack configured, play is effectively infinite-stack —
the original teaching simplification (no all-ins, single pot). With stacks, short
calls, all-ins, and layered side pots are handled, and an uncalled bet returns to
the bettor via the side-pot layering.

One documented simplification remains: ANY raise reopens the action, including an
all-in raise smaller than a full raise (real rules keep action closed for players
who already acted; the difference is rare and not worth the complexity here).
"""

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from poker.action import (
    CALL, CHECK, FOLD, RAISE, is_legal, legal_actions, parse_action, sanitize,
)
from poker.cards import Card, Deck
from poker.evaluator import category_name, evaluate
from poker.state import STREETS, GameState, HandSummary

# Sentinel for "no stack limit": large enough that no legal sequence of Limit or
# No-Limit bets can reach it, so the no-stack code path is identical to before.
INF_STACK = 10**12

# A bot is either a function `act(state) -> action`, or a class instance exposing an
# `act(self, state) -> action` method (and optionally an `on_hand_end(self, summary)`
# hook for learning across hands).
BotFn = Callable[[GameState], str]


def resolve_act(bot) -> BotFn:
    """Return the callable that chooses an action for `bot`.

    Accepts a plain function (used directly) or an object with an `act` method.
    """
    act = getattr(bot, "act", None)
    if callable(act):
        return act
    return bot


def resolve_hook(bot):
    """Return the bot's on_hand_end callable, or None if it has no learning hook."""
    hook = getattr(bot, "on_hand_end", None)
    return hook if callable(hook) else None


@dataclass
class GameConfig:
    """Betting structure for a Hold'em table.

    `betting` selects the format:
      * "limit"    — fixed raise sizes (small_bet/big_bet), raise_cap per street.
      * "no_limit" — raises carry an amount ("raise TO X" chips this street);
                     min raise = the last raise size (or the big blind), max = all-in.
                     Requires a stack to be meaningful, but tolerates none.
    `stack` is the starting stack per seat each hand (None = unlimited — classic
    teaching mode). Drivers may instead pass explicit per-seat `stacks` to
    play_hand(_gen) for carried stacks (sessions).
    """

    small_bet: int = 2          # limit: raise increment preflop and flop
    big_bet: int = 4            # limit: raise increment on turn and river
    small_blind: int = 1
    big_blind: int = 2
    raise_cap: int = 4          # limit: max bets+raises per street (1 bet + 3 raises)
    betting: str = "limit"      # "limit" | "no_limit"
    stack: Optional[int] = None  # starting stack per seat (None = unlimited)


@dataclass
class HandResult:
    """Outcome of one hand, with per-seat metrics for the stats tracker."""

    net: List[int]                              # net chip change per seat
    log: List[str] = field(default_factory=list)
    vpip_seats: Set[int] = field(default_factory=set)
    pfr_seats: Set[int] = field(default_factory=set)
    bet_raise_count: List[int] = field(default_factory=list)
    call_count: List[int] = field(default_factory=list)
    illegal_count: List[int] = field(default_factory=list)
    showdown_seats: List[int] = field(default_factory=list)
    won_showdown_seats: Set[int] = field(default_factory=set)
    # Public info for the end-of-hand summary handed to stateful bots:
    board: List[Card] = field(default_factory=list)
    betting_history: List[tuple] = field(default_factory=list)
    winners: List[int] = field(default_factory=list)
    revealed: Dict[int, List[Card]] = field(default_factory=dict)
    # Ordered, JSON-able events for animating/replaying the hand (only populated when
    # play_hand is called with record_events=True). See _EVENT TYPES_ in play_hand.
    events: List[dict] = field(default_factory=list)
    # Pot layers awarded (one entry when no all-ins): [{"amount", "winners"}].
    pots: List[dict] = field(default_factory=list)
    # Remaining stack per seat after the hand (None when stacks are unlimited).
    final_stacks: Optional[List[int]] = None


def _order_from(start: int, n: int) -> List[int]:
    """Seat indices clockwise starting at `start`."""
    return [(start + i) % n for i in range(n)]


def play_hand_gen(
    n: int,
    button: int,
    config: GameConfig,
    rng: random.Random,
    log: bool = False,
    record_events: bool = False,
    event_sink: Optional[List[dict]] = None,
    stacks: Optional[List[int]] = None,
):
    """Core hand logic as a generator, so it can be driven by bots or a live human.

    It yields a GameState each time the seat `state.my_seat` must act, and expects the
    driver to `.send((raw_action, explain))` back. On completion it returns (via
    StopIteration.value) a HandResult. `play_hand` drives it with bots; the interactive
    session (poker/interactive.py) drives it with a human in one seat.

    `stacks` (chips per seat at the start of the hand) overrides config.stack; leave
    both unset for unlimited-stack play.

    EVENT TYPES recorded when record_events=True (each has a "type" key):
      blinds   {button, sb_seat, sb, bb_seat, bb, players, stacks?}
      hole     {seat, cards:[str,str]}
      action   {seat, street, action, amount, pot, to_call, explain,
                raise_to?, all_in?, stack?}
      board    {street, cards:[str...], board:[str...]}
      showdown {board:[str...], reveals:{seat:[str,str]}, hands:{seat:name}}
      award    {winners:[seat...], pot, net:[int...], pots:[{amount, winners}]}
    """
    deck = Deck(rng)
    deck.shuffle()

    hole: List[List[Card]] = [deck.deal(2) for _ in range(n)]
    board: List[Card] = []

    limited = stacks is not None or config.stack is not None
    if stacks is not None:
        stack = [int(s) for s in stacks]
    elif config.stack is not None:
        stack = [config.stack] * n
    else:
        stack = [INF_STACK] * n
    stacks_init = list(stack)

    no_limit = config.betting == "no_limit"

    contrib = [0] * n          # total chips committed this hand, per seat
    folded = [False] * n
    history: List[tuple] = []

    result = HandResult(
        net=[0] * n,
        bet_raise_count=[0] * n,
        call_count=[0] * n,
        illegal_count=[0] * n,
    )
    lines: List[str] = []
    events: List[dict] = []

    def emit(msg: str) -> None:
        if log:
            lines.append(msg)

    def ev(event: dict) -> None:
        if record_events:
            events.append(event)
        if event_sink is not None:
            event_sink.append(event)

    def pay(seat: int, amount: int) -> int:
        """Commit up to `amount` chips from `seat` (capped by its stack)."""
        paid = min(amount, stack[seat])
        stack[seat] -= paid
        contrib[seat] += paid
        return paid

    # --- Post blinds (a short stack posts all-in for less) ---
    if n == 2:
        sb_seat, bb_seat = button, (button + 1) % n
    else:
        sb_seat, bb_seat = (button + 1) % n, (button + 2) % n
    sb_paid = pay(sb_seat, config.small_blind)
    bb_paid = pay(bb_seat, config.big_blind)
    emit(f"Seat {sb_seat} posts SB {sb_paid}, seat {bb_seat} posts BB {bb_paid}")
    blinds_event = {"type": "blinds", "button": button, "sb_seat": sb_seat,
                    "sb": sb_paid, "bb_seat": bb_seat, "bb": bb_paid,
                    "players": n}
    if limited:
        blinds_event["stacks"] = list(stack)
    ev(blinds_event)
    for s in range(n):
        ev({"type": "hole", "seat": s, "cards": [str(c) for c in hole[s]]})

    def active_seats() -> List[int]:
        return [s for s in range(n) if not folded[s]]

    def run_betting_round(street_idx: int) -> None:
        """Run one street of betting. Mutates contrib/folded/history/result."""
        preflop = street_idx == 0
        bet_size = config.small_bet if street_idx <= 1 else config.big_bet

        # street_contrib tracks chips put in *this* street only.
        street_contrib = [0] * n
        if preflop:
            street_contrib[sb_seat] = sb_paid
            street_contrib[bb_seat] = bb_paid
            current_bet = config.big_blind
            raises_so_far = 1            # the big blind is the opening bet
            last_raise = config.big_blind
            first = button if n == 2 else (button + 3) % n
        else:
            current_bet = 0
            raises_so_far = 0
            last_raise = config.big_blind   # NL: min open = one big blind
            first = (button + 1) % n     # left of button (heads-up: the BB)

        # Build the action queue clockwise from `first`, skipping folded seats.
        order = [s for s in _order_from(first, n) if not folded[s]]
        queue = deque(order)
        acted: Set[int] = set()

        while queue:
            if len(active_seats()) <= 1:
                return
            seat = queue.popleft()
            if folded[seat] or stack[seat] == 0:
                continue  # folded, or all-in: no further decisions this hand
            to_call = current_bet - street_contrib[seat]
            if seat in acted and to_call == 0:
                continue  # already matched the current bet; nothing to do
            if to_call == 0 and all(
                stack[s] == 0 for s in active_seats() if s != seat
            ):
                continue  # no one left who could call a bet: betting is over

            legal = legal_actions(
                to_call, raises_so_far, config.raise_cap,
                stack=stack[seat] if limited else None,
                betting=config.betting,
            )

            # The raise window, in "raise TO" (total street commitment) terms.
            all_in_to = street_contrib[seat] + stack[seat]
            if no_limit:
                min_raise_to = min(current_bet + last_raise, all_in_to)
                max_raise_to = all_in_to
            else:
                min_raise_to = min(current_bet + bet_size, all_in_to)
                max_raise_to = min_raise_to

            state = GameState(
                hole_cards=list(hole[seat]),
                my_seat=seat,
                my_contribution=contrib[seat],
                community_cards=list(board),
                street=STREETS[street_idx],
                pot=sum(contrib),
                to_call=to_call,
                bet_size=bet_size,
                raises_so_far=raises_so_far,
                raise_cap=config.raise_cap,
                button=button,
                num_players=n,
                active_players=active_seats(),
                contributions=list(contrib),
                betting_history=list(history),
                legal_actions=list(legal),
                betting=config.betting,
                current_bet=current_bet,
                my_street_contrib=street_contrib[seat],
                my_stack=stack[seat] if limited else None,
                stacks=list(stack) if limited else None,
                min_raise_to=min_raise_to,
                max_raise_to=max_raise_to,
            )

            raw, explain = yield state
            if not is_legal(raw, legal):
                result.illegal_count[seat] += 1
            action = sanitize(raw, legal)
            _, req_amount = parse_action(raw)

            acted.add(seat)
            history.append((seat, action))
            emit(f"  {STREETS[street_idx]}: seat {seat} {action}")

            paid = 0
            raise_to: Optional[int] = None
            if action == FOLD:
                folded[seat] = True
            elif action == CHECK:
                pass
            elif action == CALL:
                paid = pay(seat, to_call)
                street_contrib[seat] += paid
                result.call_count[seat] += 1
                if preflop:
                    result.vpip_seats.add(seat)
            elif action == RAISE:
                if no_limit:
                    if req_amount is None:
                        # Default sizing: a pot-sized raise (pot after calling).
                        pot_now = sum(contrib)
                        req_amount = street_contrib[seat] + to_call + (pot_now + to_call)
                    target = max(min_raise_to, min(req_amount, max_raise_to))
                else:
                    target = min_raise_to  # fixed size (may be an all-in for less)
                paid = pay(seat, target - street_contrib[seat])
                street_contrib[seat] += paid
                raise_to = street_contrib[seat]
                last_raise = max(raise_to - current_bet, last_raise if no_limit else 0)
                current_bet = raise_to
                raises_so_far += 1
                result.bet_raise_count[seat] += 1
                if preflop:
                    result.vpip_seats.add(seat)
                    result.pfr_seats.add(seat)
                # A raise reopens the action: everyone else must respond again.
                acted = {seat}
                queue = deque(
                    s for s in _order_from((seat + 1) % n, n)
                    if not folded[s] and s != seat
                )

            action_event = {"type": "action", "seat": seat,
                            "street": STREETS[street_idx], "action": action,
                            "amount": paid, "pot": sum(contrib),
                            "to_call": to_call, "explain": explain}
            if raise_to is not None:
                action_event["raise_to"] = raise_to
            if limited:
                action_event["stack"] = stack[seat]
                if stack[seat] == 0 and action in (CALL, RAISE):
                    action_event["all_in"] = True
            ev(action_event)

    # --- Run the four streets, dealing the board between them ---
    for street_idx in range(4):
        if len(active_seats()) <= 1:
            break
        if street_idx == 1:
            new_cards = deck.deal(3)
            board.extend(new_cards)
            emit(f"Flop: {' '.join(str(c) for c in board)}")
        elif street_idx == 2:
            new_cards = deck.deal(1)
            board.extend(new_cards)
            emit(f"Turn: {' '.join(str(c) for c in board)}")
        elif street_idx == 3:
            new_cards = deck.deal(1)
            board.extend(new_cards)
            emit(f"River: {' '.join(str(c) for c in board)}")
        else:
            new_cards = []
        if new_cards:
            ev({"type": "board", "street": STREETS[street_idx],
                "cards": [str(c) for c in new_cards],
                "board": [str(c) for c in board]})
        yield from run_betting_round(street_idx)

    # --- Award the pot(s) ---
    pot = sum(contrib)
    survivors = active_seats()
    for s in range(n):
        result.net[s] -= contrib[s]

    def award(amount: int, winners: List[int]) -> None:
        """Split `amount` among `winners`; odd chip to the earliest seat left of
        the button (the standard rule)."""
        share, remainder = divmod(amount, len(winners))
        ordered = [s for s in _order_from((button + 1) % n, n) if s in winners]
        for i, s in enumerate(ordered):
            result.net[s] += share + (remainder if i == 0 else 0)
        result.pots.append({"amount": amount, "winners": list(winners)})

    if len(survivors) == 1:
        winners = survivors
        award(pot, winners)
        emit(f"Seat {winners[0]} wins {pot} (all others folded)")
    else:
        # Showdown: best 7-card hand wins; ties split. Hole cards become public.
        result.showdown_seats = list(survivors)
        result.revealed = {s: list(hole[s]) for s in survivors}
        scores = {s: evaluate(hole[s] + board) for s in survivors}
        for s in survivors:
            emit(f"  Seat {s} shows {' '.join(str(c) for c in hole[s])} "
                 f"-> {category_name(scores[s])}")
        ev({"type": "showdown", "board": [str(c) for c in board],
            "reveals": {s: [str(c) for c in hole[s]] for s in survivors},
            "hands": {s: category_name(scores[s]) for s in survivors}})

        # Layer the pot by survivor contribution levels (side pots). With no
        # all-ins every survivor contributed the max level, so this is one pot.
        levels = sorted({contrib[s] for s in survivors})
        assigned = 0
        layers: List[Tuple[int, List[int]]] = []
        prev = 0
        for lv in levels:
            amount = sum(min(contrib[s], lv) - min(contrib[s], prev) for s in range(n))
            eligible = [s for s in survivors if contrib[s] >= lv]
            layers.append((amount, eligible))
            assigned += amount
            prev = lv
        # Safety net: any dead chips above the top survivor level (can only come
        # from a folded seat that over-contributed) land in the last layer.
        if assigned < pot:
            layers[-1] = (layers[-1][0] + (pot - assigned), layers[-1][1])

        won: Set[int] = set()
        for amount, eligible in layers:
            if amount == 0:
                continue
            best = max(scores[s] for s in eligible)
            layer_winners = [s for s in eligible if scores[s] == best]
            award(amount, layer_winners)
            won.update(layer_winners)
        winners = [s for s in _order_from((button + 1) % n, n) if s in won]
        result.won_showdown_seats = set(winners)
        emit(f"Seat(s) {winners} win {pot}")

    award_event = {"type": "award", "winners": list(winners), "pot": pot,
                   "net": list(result.net), "pots": result.pots}
    if limited:
        result.final_stacks = [stacks_init[s] + result.net[s] for s in range(n)]
        award_event["stacks"] = list(result.final_stacks)
    ev(award_event)

    result.board = list(board)
    result.betting_history = list(history)
    result.winners = list(winners)
    result.log = lines
    result.events = events
    return result


def play_hand(
    seats: List[BotFn],
    button: int,
    config: GameConfig,
    rng: Optional[random.Random] = None,
    log: bool = False,
    record_events: bool = False,
    stacks: Optional[List[int]] = None,
) -> HandResult:
    """Play one hand with bots in every seat. `seats[i]` is the bot in seat i.

    Thin driver over `play_hand_gen`: answers each yielded decision by calling that
    seat's bot (and reading its optional `last_decision` for the replay annotation).
    """
    n = len(seats)
    if n < 2:
        raise ValueError("need at least 2 players")
    rng = rng or random.Random()
    act_fns = [resolve_act(b) for b in seats]

    gen = play_hand_gen(n, button, config, rng, log, record_events, stacks=stacks)
    try:
        state = next(gen)
        while True:
            fn = act_fns[state.my_seat]
            try:
                raw = fn(state)
            except Exception:
                raw = None
            explain = getattr(seats[state.my_seat], "last_decision", None)
            state = gen.send((raw, explain))
    except StopIteration as e:
        return e.value
