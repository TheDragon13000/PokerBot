"""Cards and deck for the poker simulator.

Ranks are stored as integers 2..14 (14 = Ace) so that hand comparisons are plain
numeric comparisons. Suits are single lowercase letters: 's','h','d','c'.
"""

import random
from typing import List, Optional

# Rank values 2..14. 11=J, 12=Q, 13=K, 14=A.
RANKS = list(range(2, 15))
SUITS = ["s", "h", "d", "c"]

# For pretty-printing ranks back to their poker symbols.
_RANK_TO_CHAR = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
    10: "T", 11: "J", 12: "Q", 13: "K", 14: "A",
}
_CHAR_TO_RANK = {v: k for k, v in _RANK_TO_CHAR.items()}


class Card:
    """An immutable playing card, e.g. Card(14, 's') is the Ace of spades ('As')."""

    __slots__ = ("rank", "suit")

    def __init__(self, rank: int, suit: str):
        if rank not in _RANK_TO_CHAR:
            raise ValueError(f"invalid rank: {rank!r} (expected 2..14)")
        if suit not in SUITS:
            raise ValueError(f"invalid suit: {suit!r} (expected one of {SUITS})")
        self.rank = rank
        self.suit = suit

    @classmethod
    def from_str(cls, text: str) -> "Card":
        """Build a card from a 2-char string like 'As', 'Td', '7h'."""
        text = text.strip()
        if len(text) != 2:
            raise ValueError(f"invalid card string: {text!r}")
        rank_char, suit = text[0].upper(), text[1].lower()
        if rank_char not in _CHAR_TO_RANK:
            raise ValueError(f"invalid rank char: {text!r}")
        return cls(_CHAR_TO_RANK[rank_char], suit)

    def __str__(self) -> str:
        return f"{_RANK_TO_CHAR[self.rank]}{self.suit}"

    def __repr__(self) -> str:
        return f"Card('{self}')"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Card)
            and self.rank == other.rank
            and self.suit == other.suit
        )

    def __hash__(self) -> int:
        return hash((self.rank, self.suit))


class Deck:
    """A standard 52-card deck. Pass a random.Random for reproducible shuffles."""

    def __init__(self, rng: Optional[random.Random] = None):
        self._rng = rng or random.Random()
        self.cards: List[Card] = [Card(r, s) for s in SUITS for r in RANKS]

    def shuffle(self) -> None:
        self._rng.shuffle(self.cards)

    def deal(self, n: int = 1) -> List[Card]:
        """Remove and return the top n cards."""
        if n > len(self.cards):
            raise ValueError(f"cannot deal {n} cards, only {len(self.cards)} left")
        dealt = self.cards[:n]
        self.cards = self.cards[n:]
        return dealt

    def __len__(self) -> int:
        return len(self.cards)
