"""Interpreter that turns a visual block strategy (plain JSON) into a poker bot.

The in-game builder produces a `Strategy` dict; `StrategyBot` reads it and plays, so the
engine, match runner, replay, and stats are all reused unchanged. This is the runtime
behind the blocks-only UI (see the strategy-builder plan).

Strategy shape (all JSON-able):

    {
      "preflop": { "AA": "raise", "AKs": "raise", "72o": "fold", ... },   # 169 classes
      "flop":  { "rules": [ {"when": {...}, "action": "raise"}, ... ], "default": "check" },
      "turn":  { ... },
      "river": { ... },
    }

A postflop rule's `when` is matched against the current context; every key present must
match (a missing key is a wildcard). Rules are tried in order, first match wins, else the
street `default` is used. Supported `when` keys:

    handTier : "nothing" | "pair" | "twoPairPlus" | "monster"
    facingBet: bool                       # is there a bet to call?
    position : "ip" | "oop"               # in position (acts last) or not
    oppType  : "loose" | "tight" | "unknown"   # from showdown history
    potOdds  : "cheap" | "expensive" | "na"    # price to call (cheap = ~2:1 or better)
"""

from typing import Dict, List, Optional

from poker.action import CALL, CHECK, FOLD, RAISE
from poker.evaluator import evaluate
from poker.state import GameState, HandSummary

RANK_CHAR = {
    14: "A", 13: "K", 12: "Q", 11: "J", 10: "T",
    9: "9", 8: "8", 7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2",
}
RANKS_DESC = [14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2]

# The four made-hand tiers, by evaluator category (see poker/evaluator.py):
#   0 high card -> nothing; 1 pair -> pair; 2-3 two pair/trips -> twoPairPlus;
#   4+ straight and up -> monster.
TIERS = ["nothing", "pair", "twoPairPlus", "monster"]

TIER_LABEL = {
    "nothing": "Nothing",
    "pair": "A pair",
    "twoPairPlus": "Two pair / trips",
    "monster": "Monster",
}


def hand_class(cards) -> str:
    """Canonical preflop class for 2 hole cards, e.g. 'AA', 'AKs', '72o'."""
    a, b = cards[0], cards[1]
    hi, lo = (a, b) if a.rank >= b.rank else (b, a)
    if hi.rank == lo.rank:
        return RANK_CHAR[hi.rank] * 2
    suited = "s" if hi.suit == lo.suit else "o"
    return f"{RANK_CHAR[hi.rank]}{RANK_CHAR[lo.rank]}{suited}"


def all_hand_classes() -> List[str]:
    """All 169 canonical classes, in grid order (row/col over ranks A..2)."""
    out: List[str] = []
    for i, hi in enumerate(RANKS_DESC):
        for j, lo in enumerate(RANKS_DESC):
            if i == j:
                out.append(RANK_CHAR[hi] * 2)
            elif j > i:  # upper triangle: suited
                out.append(f"{RANK_CHAR[hi]}{RANK_CHAR[lo]}s")
            else:        # lower triangle: offsuit (higher rank first)
                out.append(f"{RANK_CHAR[lo]}{RANK_CHAR[hi]}o")
    return out


def made_tier(cards) -> str:
    """Bucket the best hand from 5+ cards into a tier name."""
    cat = evaluate(cards)[0]
    if cat == 0:
        return "nothing"
    if cat == 1:
        return "pair"
    if cat in (2, 3):
        return "twoPairPlus"
    return "monster"


class StrategyBot:
    """Plays according to a block Strategy dict. Stateful only to profile opponents."""

    LOOSE_THRESHOLD = 1.0
    MIN_SAMPLES = 3

    def __init__(self, strategy: Optional[dict] = None):
        self.strategy = strategy or {}
        self._showdowns: Dict[int, List[int]] = {}
        # Human-readable reason for the most recent decision (surfaced in replays).
        self.last_decision: Optional[str] = None

    # --- opponent profiling (feeds the oppType condition) ---
    def on_hand_end(self, summary: HandSummary) -> None:
        for seat, cards in summary.revealed.items():
            self._showdowns.setdefault(seat, []).append(evaluate(cards + summary.board)[0])

    def _looseness(self, seat: int) -> Optional[float]:
        cats = self._showdowns.get(seat, [])
        if len(cats) < self.MIN_SAMPLES:
            return None
        return sum(cats) / len(cats)

    def _opp_type(self, state: GameState) -> str:
        vals = [self._looseness(s) for s in state.active_players if s != state.my_seat]
        vals = [v for v in vals if v is not None]
        if not vals:
            return "unknown"
        return "loose" if min(vals) <= self.LOOSE_THRESHOLD else "tight"

    @staticmethod
    def _pot_odds(state: GameState) -> str:
        """'cheap' if calling gets ~2:1 or better, 'expensive' otherwise, 'na' if no bet."""
        if state.to_call <= 0:
            return "na"
        price = state.to_call / (state.pot + state.to_call)
        return "cheap" if price <= 0.34 else "expensive"

    # --- decision making ---
    def act(self, state: GameState) -> str:
        if state.street == "preflop":
            grid = self.strategy.get("preflop", {})
            cls = hand_class(state.hole_cards)
            action = grid.get(cls, FOLD)
            self.last_decision = f"Preflop {cls} → {action}"
            return self._legalize(action, state)

        policy = self.strategy.get(state.street) or {}
        tier = made_tier(state.hole_cards + state.community_cards)
        ctx = {
            "handTier": tier,
            "facingBet": state.to_call > 0,
            "position": "ip" if state.my_seat == state.button else "oop",
            "oppType": self._opp_type(state),
            "potOdds": self._pot_odds(state),
        }
        for rule in policy.get("rules", []):
            if self._matches(rule.get("when", {}), ctx):
                action = rule.get("action", FOLD)
                self.last_decision = f"{TIER_LABEL.get(tier, tier)} → {action}"
                return self._legalize(action, state)
        action = policy.get("default", CHECK)
        self.last_decision = f"{TIER_LABEL.get(tier, tier)} → {action}"
        return self._legalize(action, state)

    @staticmethod
    def _matches(when: dict, ctx: dict) -> bool:
        return all(ctx.get(k) == v for k, v in when.items())

    @staticmethod
    def _legalize(action: str, state: GameState) -> str:
        """Coerce an intended action to a legal one (the engine also sanitizes)."""
        legal = state.legal_actions
        if action in legal:
            return action
        if action == RAISE:
            return CALL if CALL in legal else CHECK
        if action == CALL:
            return CHECK if CHECK in legal else FOLD
        # check/fold requested but illegal (e.g. fold for free) -> safest legal move
        return CHECK if CHECK in legal else (CALL if CALL in legal else FOLD)


# --- Reference strategies: double as defaults, examples, and test fixtures ----------

def _preflop_all(action: str) -> Dict[str, str]:
    return {cls: action for cls in all_hand_classes()}


def folder_strategy() -> dict:
    """Folds to any bet, checks when free — mirrors bots.examples.folder."""
    facing_fold = {"rules": [{"when": {"facingBet": True}, "action": FOLD}],
                   "default": CHECK}
    return {"preflop": _preflop_all(FOLD),
            "flop": facing_fold, "turn": facing_fold, "river": facing_fold}


def caller_strategy() -> dict:
    """Calls/checks everything down — mirrors bots.examples.caller."""
    passive = {"rules": [], "default": CHECK}  # to_call>0 -> CHECK legalizes to CALL
    return {"preflop": _preflop_all(CALL),
            "flop": passive, "turn": passive, "river": passive}


def value_strategy() -> dict:
    """A simple value bot: raise made hands, otherwise check/call. Beats the Caller."""
    street = {
        "rules": [
            {"when": {"handTier": "monster"}, "action": RAISE},
            {"when": {"handTier": "twoPairPlus"}, "action": RAISE},
            {"when": {"handTier": "pair"}, "action": RAISE},
        ],
        "default": CHECK,
    }
    return {"preflop": _preflop_all(CALL),
            "flop": dict(street), "turn": dict(street), "river": dict(street)}
