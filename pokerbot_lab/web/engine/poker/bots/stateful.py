"""Stateful (class-based) example bots.

A stateful bot is an *object* with an `act(self, state) -> action` method, and an
optional `on_hand_end(self, summary)` hook that lets it learn across hands. Because
each bot keeps a fixed seat for the whole match, an instance can build a per-opponent
profile that persists from hand to hand.

Register a fresh instance per seat, e.g.:

    bots = {"profiler": ProfilingBot(), "caller": caller}
    run_match(bots, hands=20000)
"""

from typing import Dict, List, Optional

from poker.action import CALL, CHECK, FOLD, RAISE
from poker.evaluator import evaluate
from poker.state import GameState, HandSummary


def _last_aggressor(history: List[tuple], me: int) -> Optional[int]:
    """Seat of the most recent opponent to raise this hand, or None."""
    for seat, action in reversed(history):
        if action == RAISE and seat != me:
            return seat
    return None


class ProfilingBot:
    """Tight-aggressive baseline that adapts using opponents' showdown reveals.

    Every time an opponent shows down, we record the strength (category 0..8) of the
    hand they revealed. Opponents who repeatedly show *weak* hands are "loose" (calling
    stations / bluffers); those who only show strong hands are "tight" (rocks).

    We exploit the profile two ways:
      * Thin value: raise one-pair hands when a loose opponent is in the pot.
      * Hero calls: call down with a weak hand only when the bettor is known-loose.
    With no data yet, it just plays straightforward tight-aggressive poker.
    """

    LOOSE_THRESHOLD = 1.0   # avg revealed category at/below this == "loose"
    MIN_SAMPLES = 3         # showdowns needed before trusting a profile

    def __init__(self) -> None:
        # seat -> list of revealed hand categories (0..8) at showdown
        self._showdowns: Dict[int, List[int]] = {}

    # --- Learning hook ---------------------------------------------------
    def on_hand_end(self, summary: HandSummary) -> None:
        for seat, cards in summary.revealed.items():
            score = evaluate(cards + summary.board)
            self._showdowns.setdefault(seat, []).append(score[0])

    def _looseness(self, seat: Optional[int]) -> Optional[float]:
        """Average revealed category for a seat; lower == looser. None if unknown."""
        if seat is None:
            return None
        cats = self._showdowns.get(seat, [])
        if len(cats) < self.MIN_SAMPLES:
            return None
        return sum(cats) / len(cats)

    def _loose_opponent_in_pot(self, state: GameState) -> bool:
        for s in state.active_players:
            if s == state.my_seat:
                continue
            looseness = self._looseness(s)
            if looseness is not None and looseness <= self.LOOSE_THRESHOLD:
                return True
        return False

    # --- Decision making -------------------------------------------------
    def act(self, state: GameState) -> str:
        if state.street == "preflop":
            r1, r2 = sorted((c.rank for c in state.hole_cards), reverse=True)
            pair = r1 == r2
            strong = pair and r1 >= 9
            playable = pair or (r1 + r2) >= 22
            if strong and RAISE in state.legal_actions:
                return RAISE
            if playable:
                return CHECK if state.to_call == 0 else CALL
            return CHECK if state.to_call == 0 else FOLD

        category = evaluate(state.hole_cards + state.community_cards)[0]

        if RAISE in state.legal_actions:
            if category >= 2:                                   # two pair+: value raise
                return RAISE
            if category >= 1 and self._loose_opponent_in_pot(state):
                return RAISE                                    # thin value vs a station
        if category >= 1:                                       # at least a pair
            return CHECK if state.to_call == 0 else CALL
        if state.to_call == 0:
            return CHECK

        # No made hand and facing a bet: hero-call only a known-loose aggressor.
        aggressor = _last_aggressor(state.betting_history, state.my_seat)
        if self._looseness(aggressor) is not None and \
                self._looseness(aggressor) <= self.LOOSE_THRESHOLD:
            return CALL
        return FOLD
