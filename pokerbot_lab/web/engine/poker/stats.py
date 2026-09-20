"""Accumulates per-bot statistics across many hands."""

from dataclasses import dataclass, field
from typing import List

from poker.engine import HandResult


@dataclass
class BotStats:
    name: str
    hands: int = 0
    net: int = 0                       # cumulative net chips
    vpip: int = 0                      # hands voluntarily put money in preflop
    pfr: int = 0                       # hands raised preflop
    bets_raises: int = 0               # total bets/raises (for aggression factor)
    calls: int = 0                     # total calls (for aggression factor)
    showdowns: int = 0                 # hands seen to showdown
    showdowns_won: int = 0
    illegal: int = 0                   # sanitized / invalid actions returned
    hands_won: int = 0                 # hands that ended net-positive
    biggest_win: int = 0               # largest single-hand net gain
    biggest_loss: int = 0              # largest single-hand net loss (<= 0)
    bankroll: List[int] = field(default_factory=list)  # cumulative net per hand

    @property
    def vpip_pct(self) -> float:
        return 100.0 * self.vpip / self.hands if self.hands else 0.0

    @property
    def pfr_pct(self) -> float:
        return 100.0 * self.pfr / self.hands if self.hands else 0.0

    @property
    def win_pct(self) -> float:
        return 100.0 * self.hands_won / self.hands if self.hands else 0.0

    @property
    def showdown_pct(self) -> float:
        return 100.0 * self.showdowns / self.hands if self.hands else 0.0

    @property
    def aggression_factor(self) -> float:
        return self.bets_raises / self.calls if self.calls else float("inf")

    def bb_per_100(self, big_blind: int) -> float:
        if not self.hands:
            return 0.0
        return self.net / big_blind / self.hands * 100.0


class Stats:
    """Tracks one BotStats per seat. Seats keep fixed bots; the button rotates."""

    def __init__(self, names: List[str], big_blind: int):
        self.big_blind = big_blind
        self.seats: List[BotStats] = [BotStats(name=nm) for nm in names]
        # Optional recorded hands (each a list of event dicts) for replay/animation.
        self.replays: List[List[dict]] = []
        # Curated replays (see run_match(curate=...)): the seat-0 player's biggest
        # wins and losses, each {"kind", "hand", "net", "events"}.
        self.curated: List[dict] = []
        # Fixed-stack session fields (see run_session): the player's carried stack
        # after each hand, whether they busted, and the final stack.
        self.session_stack: List[int] = []
        self.session_busted: bool = False
        self.session_final_stack: int = 0

    def record(self, result: HandResult) -> None:
        for seat, bs in enumerate(self.seats):
            hand_net = result.net[seat]
            bs.hands += 1
            bs.net += hand_net
            bs.bankroll.append(bs.net)
            if hand_net > 0:
                bs.hands_won += 1
            bs.biggest_win = max(bs.biggest_win, hand_net)
            bs.biggest_loss = min(bs.biggest_loss, hand_net)
            if seat in result.vpip_seats:
                bs.vpip += 1
            if seat in result.pfr_seats:
                bs.pfr += 1
            bs.bets_raises += result.bet_raise_count[seat]
            bs.calls += result.call_count[seat]
            bs.illegal += result.illegal_count[seat]
            if seat in result.showdown_seats:
                bs.showdowns += 1
            if seat in result.won_showdown_seats:
                bs.showdowns_won += 1

    def ranked(self) -> List[BotStats]:
        """Bots sorted best-to-worst by bb/100."""
        return sorted(
            self.seats, key=lambda b: b.bb_per_100(self.big_blind), reverse=True
        )

    def summary_table(self) -> str:
        header = (
            f"{'Bot':<18}{'Hands':>8}{'Net':>10}{'bb/100':>10}"
            f"{'VPIP%':>8}{'PFR%':>8}{'AF':>7}{'SD won':>9}{'Illegal':>9}"
        )
        rows = [header, "-" * len(header)]
        for b in self.ranked():
            af = b.aggression_factor
            af_str = "inf" if af == float("inf") else f"{af:.2f}"
            rows.append(
                f"{b.name:<18}{b.hands:>8}{b.net:>10}"
                f"{b.bb_per_100(self.big_blind):>10.2f}"
                f"{b.vpip_pct:>8.1f}{b.pfr_pct:>8.1f}{af_str:>7}"
                f"{b.showdowns_won:>9}{b.illegal:>9}"
            )
        return "\n".join(rows)
