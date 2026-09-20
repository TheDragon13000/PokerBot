"""Monte-Carlo equity calculation, built on the existing card engine.

EQUITY = your expected share of the pot if every remaining card is dealt out and the
hand goes to showdown against the given opponents. We estimate it by simulating many
random run-outs and averaging your share. This is the Law of Large Numbers in action
(the same idea as the coin-flip demo): the average converges to the true equity as the
number of trials grows.

For a single trial the share is:
    1.0           if you have the best hand alone
    1 / (k + 1)   if you tie with k opponents (you split the pot)
    0.0           if someone beats you
Averaging that share over all trials gives equity. Heads-up with no splits this reduces
to the familiar formula  (wins + ties/2) / trials.

A note on POSITION: raw all-in equity depends only on the *cards* -- your hand, the
board, how many opponents, and any opponent cards you know -- not on your seat. Position
matters when you turn equity into a *decision* (pot odds, who still has to act, future
betting streets), which is the next topic. The card-based knob that moves equity the most
is the number of opponents, so that's the main thing to vary here.
"""

import random
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Union

from poker.cards import RANKS, SUITS, Card
from poker.evaluator import evaluate

# A card may be given as a Card object or a 2-char string like "As" or "Td".
CardSpec = Union[Card, str]


def to_cards(spec: Optional[Sequence[CardSpec]]) -> List[Card]:
    """Normalize a list of cards-or-strings into a list of Card objects."""
    if spec is None:
        return []
    return [c if isinstance(c, Card) else Card.from_str(c) for c in spec]


def _full_deck() -> List[Card]:
    return [Card(r, s) for s in SUITS for r in RANKS]


@dataclass
class EquityResult:
    """The outcome of an equity simulation."""

    hero: List[Card]
    board: List[Card]
    num_opponents: int
    trials: int
    wins: int
    ties: int
    losses: int
    equity: float                       # expected pot share in [0, 1]
    villains: List[List[Card]] = field(default_factory=list)

    @property
    def win_pct(self) -> float:
        return 100.0 * self.wins / self.trials

    @property
    def tie_pct(self) -> float:
        return 100.0 * self.ties / self.trials

    def __str__(self) -> str:
        hero = " ".join(str(c) for c in self.hero)
        board = " ".join(str(c) for c in self.board) or "(preflop)"
        return (
            f"{hero} vs {self.num_opponents} opp on [{board}]: "
            f"equity {self.equity * 100:.1f}%  "
            f"(win {self.win_pct:.1f}% / tie {self.tie_pct:.1f}% / "
            f"lose {100.0 * self.losses / self.trials:.1f}%, n={self.trials})"
        )


def equity(
    hero: Sequence[CardSpec],
    num_opponents: int = 1,
    villains: Optional[Sequence[Sequence[CardSpec]]] = None,
    board: Optional[Sequence[CardSpec]] = None,
    dead: Optional[Sequence[CardSpec]] = None,
    trials: int = 10_000,
    seed: Optional[int] = None,
) -> EquityResult:
    """Estimate the equity of `hero` by Monte-Carlo simulation.

    Modular options (mix and match freely):
      hero          : your 2 hole cards, e.g. ["As", "Ah"].
      num_opponents : how many opponents are in the pot (default 1). Opponents with no
                      known cards get random hole cards each trial.
      villains      : known opponent hands, e.g. [["4h", "6s"]]. Any opponents beyond
                      those listed (up to num_opponents) are random.
      board         : known community cards (0, 3, 4, or 5). Missing board cards are
                      dealt randomly each trial. Use this to test flop/turn spots.
      dead          : cards known to be out of play (e.g. folded/exposed) so they are
                      never dealt to opponents or the board.
      trials        : number of simulated run-outs (more = more precise).
      seed          : fix for reproducible results.

    Returns an EquityResult.
    """
    rng = random.Random(seed)

    hero_cards = to_cards(hero)
    if len(hero_cards) != 2:
        raise ValueError("hero must be exactly 2 cards")

    board_cards = to_cards(board)
    if len(board_cards) not in (0, 3, 4, 5):
        raise ValueError("board must have 0, 3, 4, or 5 cards")

    dead_cards = to_cards(dead)
    villain_known = [to_cards(v) for v in (villains or [])]
    for v in villain_known:
        if len(v) != 2:
            raise ValueError("each known villain hand must be exactly 2 cards")

    n_opp = max(num_opponents, len(villain_known))
    n_random_opp = n_opp - len(villain_known)
    if n_opp < 1:
        raise ValueError("need at least 1 opponent")

    # Pull every known card out of the deck and check for duplicates.
    known = hero_cards + board_cards + dead_cards
    for v in villain_known:
        known += v
    used = set(known)
    if len(used) != len(known):
        raise ValueError("duplicate card specified across hero/board/villains/dead")
    deck = [c for c in _full_deck() if c not in used]

    need_board = 5 - len(board_cards)
    draws_per_trial = need_board + 2 * n_random_opp
    if draws_per_trial > len(deck):
        raise ValueError("not enough cards left in the deck for this setup")

    wins = ties = losses = 0
    equity_sum = 0.0

    for _ in range(trials):
        sample = rng.sample(deck, draws_per_trial)
        i = 0
        opp_hands = list(villain_known)
        for _ in range(n_random_opp):
            opp_hands.append(sample[i:i + 2])
            i += 2
        full_board = board_cards + sample[i:i + need_board]

        hero_score = evaluate(hero_cards + full_board)
        opp_scores = [evaluate(o + full_board) for o in opp_hands]
        best_opp = max(opp_scores)

        if hero_score > best_opp:
            wins += 1
            equity_sum += 1.0
        elif hero_score < best_opp:
            losses += 1
        else:
            tied_opponents = sum(1 for s in opp_scores if s == hero_score)
            equity_sum += 1.0 / (tied_opponents + 1)
            ties += 1

    return EquityResult(
        hero=hero_cards,
        board=board_cards,
        num_opponents=n_opp,
        trials=trials,
        wins=wins,
        ties=ties,
        losses=losses,
        equity=equity_sum / trials,
        villains=villain_known,
    )


# --- Turning equity into a decision: pot odds ---------------------------------
# (The bridge to the next lesson.) Pot odds tell you the equity you need to break even
# on a call. Compare that threshold to the equity computed above.

def required_equity(to_call: int, pot: int) -> float:
    """Minimum equity needed to break even on a call.

    `pot` is the pot size *before* you put your call in. You are risking `to_call` to
    win `pot`, so you must win at least  to_call / (pot + to_call)  of the time.
    """
    if to_call < 0 or pot < 0:
        raise ValueError("pot and to_call must be non-negative")
    if to_call == 0:
        return 0.0
    return to_call / (pot + to_call)


def should_call(eq: float, to_call: int, pot: int) -> bool:
    """True if calling is profitable given your equity (ignores future betting)."""
    return eq >= required_equity(to_call, pot)
