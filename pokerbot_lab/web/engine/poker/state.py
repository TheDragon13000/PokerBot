"""The read-only view of a hand that gets passed to a bot's act(state) function."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from poker.cards import Card

# Street names, indexed 0..3.
STREETS = ["preflop", "flop", "turn", "river"]


@dataclass
class GameState:
    """Everything a bot is allowed to know when it acts.

    A bot receives one of these and must return an action string (see poker.action).
    All fields describe the situation from the acting bot's point of view.
    """

    # --- The acting bot's private info ---
    hole_cards: List[Card]            # this bot's 2 hole cards
    my_seat: int                      # this bot's seat index
    my_contribution: int              # chips this bot has put in this hand so far

    # --- Public board / pot info ---
    community_cards: List[Card]       # 0, 3, 4, or 5 shared cards
    street: str                       # "preflop" | "flop" | "turn" | "river"
    pot: int                          # total chips in the pot right now
    to_call: int                      # chips needed to call (0 means checking is free)
    bet_size: int                     # the fixed raise increment on this street
    raises_so_far: int                # number of bets/raises made this street
    raise_cap: int                    # max bets/raises allowed this street

    # --- Table info ---
    button: int                       # seat index of the dealer button
    num_players: int                  # players who started this hand
    active_players: List[int]         # seats still in the hand (not folded)
    contributions: List[int]          # chips each seat has put in this hand

    # --- History & convenience ---
    betting_history: List[Tuple[int, str]]  # (seat, action) in order, this hand
    legal_actions: List[str] = field(default_factory=list)  # what you may return now

    # --- Betting format & stacks (None stack fields = unlimited/limit-classic) ---
    betting: str = "limit"                  # "limit" | "no_limit"
    current_bet: int = 0                    # the street's current bet level (to match)
    my_street_contrib: int = 0              # chips I have put in THIS street
    my_stack: Optional[int] = None          # my remaining chips (None = unlimited)
    stacks: Optional[List[int]] = None      # remaining chips per seat (None = unlimited)
    # Raise window, in "raise TO" terms (total street commitment after raising).
    # In Limit min == max (fixed size); in No-Limit max is an all-in.
    min_raise_to: int = 0
    max_raise_to: int = 0


@dataclass
class HandSummary:
    """Public recap of a finished hand, passed to a bot's on_hand_end(summary) hook.

    Contains only information a real player would have seen: every action is public,
    but hole cards appear in `revealed` ONLY for seats that went to showdown. Hands
    that ended by everyone folding reveal no cards. Seat indices are stable for the
    whole match, so a bot can build a per-opponent profile across many hands.
    """

    button: int
    num_players: int
    board: List[Card]                          # the community cards dealt this hand
    betting_history: List[Tuple[int, str]]     # (seat, action) in order
    net: List[int]                             # chip change per seat this hand
    winners: List[int]                         # seat(s) that won the pot
    showdown_seats: List[int]                  # seats that reached showdown
    revealed: Dict[int, List[Card]] = field(default_factory=dict)  # showdown hole cards
