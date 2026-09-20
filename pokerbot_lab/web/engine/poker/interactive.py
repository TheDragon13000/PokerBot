"""Interactive (human-in-the-seat) play, driving the same engine as the bots.

`InteractiveMatch` plays a continuous match: the human sits in seat 0 against one or
more bots (heads-up or multiway), the button rotates each hand, and the human's
running net is tracked. It drives `play_hand_gen` (poker/engine.py), auto-answering
the bots' turns and pausing whenever the human must act. Events are streamed as they
happen so the UI can animate opponents' moves before presenting the human's options.

Stack modes:
  * stack=None            — unlimited (classic teaching mode; the default).
  * stack=S               — every seat gets S chips each hand (all-ins possible).
  * stack=S, carry=True   — SURVIVAL: the human's stack carries across hands while
                            bots refill; when it hits 0 the session reports busted.

The opponents' hole cards are never streamed live (only the human's own) — they
appear only via the showdown event if the hand gets there, just like real poker.
"""

from typing import List, Optional

from poker.engine import GameConfig, play_hand_gen, resolve_act
from poker.state import GameState

HUMAN = 0


class InteractiveMatch:
    def __init__(self, opponents, config: Optional[GameConfig] = None,
                 seed: Optional[int] = None, fixed_button: Optional[int] = None,
                 stack: Optional[int] = None, carry: bool = False):
        """`opponents` is a bot or a list of bots (seats 1..n in order).

        `fixed_button` pins the dealer button to one seat for every hand (used by
        Academy position drills: button==human -> always in position postflop, and
        vice versa). Default None keeps the normal per-hand rotation.
        """
        import random
        if not isinstance(opponents, (list, tuple)):
            opponents = [opponents]
        if not opponents:
            raise ValueError("need at least one opponent")
        self.opponents = list(opponents)
        self.opp_acts = [resolve_act(o) for o in self.opponents]
        self.n = 1 + len(self.opponents)
        self.config = config or GameConfig()
        self.rng = random.Random(seed)
        self.fixed_button = fixed_button
        self.button = fixed_button if fixed_button is not None else 0
        self.stack = stack if stack is not None else self.config.stack
        self.carry = carry and self.stack is not None
        self.player_stack: Optional[int] = self.stack
        self.busted = False
        self.net = [0] * self.n
        self.hands_played = 0
        self._gen = None
        self._live: List[dict] = []
        self._consumed = 0
        self._pending: Optional[GameState] = None
        self._done: Optional[dict] = None
        self._stacks: Optional[List[int]] = None  # after the last finished hand

    # --- generator plumbing ---
    def _start_gen(self):
        try:
            return next(self._gen)
        except StopIteration as e:
            self._finish(e.value)
            return None

    def _send(self, value):
        try:
            return self._gen.send(value)
        except StopIteration as e:
            self._finish(e.value)
            return None

    def _auto_opponents(self, state: Optional[GameState]) -> Optional[GameState]:
        """Answer bot turns until it's the human's turn (or the hand ends)."""
        while state is not None and state.my_seat != HUMAN:
            bot_index = state.my_seat - 1
            try:
                raw = self.opp_acts[bot_index](state)
            except Exception:
                raw = None
            explain = getattr(self.opponents[bot_index], "last_decision", None)
            state = self._send((raw, explain))
        return state

    def _finish(self, result):
        self.hands_played += 1
        for s in range(self.n):
            self.net[s] += result.net[s]
        self._stacks = result.final_stacks
        if self.carry:
            self.player_stack += result.net[HUMAN]
            self.busted = self.player_stack <= 0
        self._done = {
            "winners": list(result.winners),
            "handNet": result.net[HUMAN],
            "youWon": HUMAN in result.winners,
            "pots": result.pots,
        }
        if self.fixed_button is None:
            self.button = (self.button + 1) % self.n  # rotate for the next hand

    # --- public API (returns JSON-able payloads) ---
    def _hand_stacks(self) -> Optional[List[int]]:
        """Per-seat starting stacks for the next hand, or None (unlimited)."""
        if self.stack is None:
            return None
        player = self.player_stack if self.carry else self.stack
        return [player] + [self.stack] * (self.n - 1)

    def start_hand(self) -> dict:
        if self.busted:
            return self._payload()  # no more hands: the session is over
        self._live = []
        self._consumed = 0
        self._done = None
        self._pending = None
        self._gen = play_hand_gen(self.n, self.button, self.config, self.rng,
                                  record_events=True, event_sink=self._live,
                                  stacks=self._hand_stacks())
        state = self._start_gen()
        self._pending = self._auto_opponents(state)
        return self._payload()

    def act(self, action: str) -> dict:
        if self._pending is None or self._done is not None:
            return self._payload()
        state = self._send((action, None))
        self._pending = self._auto_opponents(state)
        return self._payload()

    def _pending_view(self) -> Optional[dict]:
        s = self._pending
        if s is None or self._done is not None:
            return None
        return {
            "legal": list(s.legal_actions),
            "toCall": s.to_call,
            "pot": s.pot,
            "street": s.street,
            "hole": [str(c) for c in s.hole_cards],
            "board": [str(c) for c in s.community_cards],
            "betSize": s.bet_size,
            "betting": s.betting,
            "currentBet": s.current_bet,
            "streetContrib": s.my_street_contrib,
            "myStack": s.my_stack,
            "minRaiseTo": s.min_raise_to,
            "maxRaiseTo": s.max_raise_to,
        }

    def _payload(self) -> dict:
        new = self._live[self._consumed:]
        self._consumed = len(self._live)
        # Hide the bots' hole cards during live play (reveal only at showdown).
        live = [e for e in new if not (e["type"] == "hole" and e["seat"] != HUMAN)]
        # Best current stack snapshot: mid-decision from the game state, otherwise
        # the stacks after the last finished hand.
        stacks = None
        if self.stack is not None:
            stacks = self._pending.stacks if self._pending is not None else self._stacks
        return {
            "events": live,
            "pending": self._pending_view(),
            "done": self._done,
            "net": list(self.net),
            "handsPlayed": self.hands_played,
            "button": self.button,
            "humanSeat": HUMAN,
            "players": self.n,
            "stacks": stacks,
            "carry": self.carry,
            "playerStack": self.player_stack if self.carry else None,
            "busted": self.busted,
        }
