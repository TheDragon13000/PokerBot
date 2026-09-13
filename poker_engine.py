"""
poker_engine.py
================
A headless No-Limit Texas Hold'em engine, used to let a player-written
bot function play ranked, heads-up matches against built-in easy / medium
/ hard bots. As the player's bot wins matches, the opponent tier gets
harder automatically (progress is saved to disk between runs).

This module has NO input() calls anywhere -- it is safe to run from a
non-interactive process (e.g. launched by a game via OS.execute()) with
its stdout captured and shown elsewhere.

Built-in bot difficulty summary
--------------------------------
- easy:   Mostly random decisions, loosely biased toward calling. Doesn't
          really evaluate hand strength. Easy to beat.
- medium: Uses a quick hand-strength heuristic (preflop hand quality,
          postflop made-hand category) compared against pot odds, with a
          little randomness. No lookahead/simulation.
- hard:   Runs a Monte Carlo simulation each decision to estimate its
          real equity (win probability) against the other active
          players, then compares that to the pot odds it's being
          offered, with a small chance of bluffing either way.

No external dependencies -- pure Python standard library only.
"""

import random
import os
import json
import sys
from itertools import combinations
from collections import Counter

# On Windows, output piped out of a process (like OS.execute() does) often
# defaults to the legacy 'cp1252' encoding, which can't represent the suit
# symbols (♠♥♦♣) this module prints -- that crashes with a
# UnicodeEncodeError the instant a card is shown. Forcing UTF-8 here fixes
# it regardless of the OS or how the script is being run.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Cards & deck
# ---------------------------------------------------------------------------

RANK_ORDER = "23456789TJQKA"
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANK_ORDER)}
SUITS = "shdc"
SUIT_SYMBOL = {"s": "\u2660", "h": "\u2665", "d": "\u2666", "c": "\u2663"}


def make_deck():
    return [(RANK_VALUE[r], s) for r in RANK_ORDER for s in SUITS]


def card_str(card):
    rank_val, suit = card
    rank_char = RANK_ORDER[rank_val - 2]
    return f"{rank_char}{SUIT_SYMBOL[suit]}"


def cards_str(cards):
    return " ".join(card_str(c) for c in cards) if cards else "(none)"


# ---------------------------------------------------------------------------
# Hand evaluation
# ---------------------------------------------------------------------------

HAND_NAMES = {
    8: "Straight Flush",
    7: "Four of a Kind",
    6: "Full House",
    5: "Flush",
    4: "Straight",
    3: "Three of a Kind",
    2: "Two Pair",
    1: "Pair",
    0: "High Card",
}


def hand_rank(cards5):
    """Rank a single 5-card hand. Returns a tuple that can be compared
    directly with other such tuples -- bigger is better."""
    ranks = sorted((c[0] for c in cards5), reverse=True)
    suits = [c[1] for c in cards5]
    is_flush = len(set(suits)) == 1
    unique_ranks = sorted(set(ranks), reverse=True)

    is_straight = False
    straight_high = None
    if len(unique_ranks) == 5 and unique_ranks[0] - unique_ranks[4] == 4:
        is_straight = True
        straight_high = unique_ranks[0]
    elif set(unique_ranks) == {14, 5, 4, 3, 2}:  # wheel: A-2-3-4-5
        is_straight = True
        straight_high = 5

    counts = Counter(ranks)
    by_count = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    count_vals = [c for _, c in by_count]

    if is_straight and is_flush:
        return (8, straight_high)
    if count_vals[0] == 4:
        four_rank = by_count[0][0]
        kicker = max(r for r in ranks if r != four_rank)
        return (7, four_rank, kicker)
    if count_vals[0] == 3 and count_vals[1] >= 2:
        return (6, by_count[0][0], by_count[1][0])
    if is_flush:
        return (5, *ranks)
    if is_straight:
        return (4, straight_high)
    if count_vals[0] == 3:
        trip = by_count[0][0]
        kickers = sorted((r for r in ranks if r != trip), reverse=True)
        return (3, trip, *kickers)
    if count_vals[0] == 2 and count_vals[1] == 2:
        pair_hi, pair_lo = sorted((by_count[0][0], by_count[1][0]), reverse=True)
        kicker = max(r for r in ranks if r not in (pair_hi, pair_lo))
        return (2, pair_hi, pair_lo, kicker)
    if count_vals[0] == 2:
        pair = by_count[0][0]
        kickers = sorted((r for r in ranks if r != pair), reverse=True)
        return (1, pair, *kickers)
    return (0, *ranks)


def best_hand_rank(cards):
    """Best 5-card ranking out of 5, 6, or 7 cards."""
    if len(cards) == 5:
        return hand_rank(cards)
    return max(hand_rank(list(combo)) for combo in combinations(cards, 5))


def hand_description(rank_tuple):
    return HAND_NAMES[rank_tuple[0]]


# ---------------------------------------------------------------------------
# Equity estimation (Monte Carlo) -- used by the "hard" bot
# ---------------------------------------------------------------------------

def estimate_equity(hole, community, num_opponents, trials=200):
    """Rough win probability for `hole` against `num_opponents` random hands,
    given the community cards seen so far."""
    if num_opponents <= 0:
        return 1.0
    known = set(hole) | set(community)
    deck = [c for c in make_deck() if c not in known]
    needed = 5 - len(community)
    wins = 0.0

    for _ in range(trials):
        random.shuffle(deck)
        i = 0
        opp_holes = []
        for _ in range(num_opponents):
            opp_holes.append([deck[i], deck[i + 1]])
            i += 2
        sim_community = community + deck[i:i + needed]

        my_rank = best_hand_rank(hole + sim_community)
        best_opp_rank = max(best_hand_rank(oh + sim_community) for oh in opp_holes)

        if my_rank > best_opp_rank:
            wins += 1
        elif my_rank == best_opp_rank:
            wins += 0.5

    return wins / trials


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class Player:
    def __init__(self, name, stack, difficulty=None, decision_fn=None):
        self.name = name
        self.stack = stack
        self.difficulty = difficulty      # 'easy' / 'medium' / 'hard' for a built-in bot
        self.decision_fn = decision_fn    # a player-written bot function, if any
        self.reset_hand()

    def reset_hand(self):
        self.hole = []
        self.folded = False
        self.all_in = False
        self.committed = 0     # total chips put in this whole hand (for side pots)
        self.current_bet = 0   # chips put in during the current betting round

    @property
    def active(self):
        """Can still take an action (hasn't folded, has chips left)."""
        return not self.folded and self.stack > 0

    def __repr__(self):
        return self.name


# ---------------------------------------------------------------------------
# Bot AI
# ---------------------------------------------------------------------------

def preflop_strength(hole):
    """Very rough starting-hand quality score, roughly 4-40."""
    r1, s1 = hole[0]
    r2, s2 = hole[1]
    hi, lo = max(r1, r2), min(r1, r2)
    suited = s1 == s2
    pair = r1 == r2

    score = hi + lo
    if pair:
        score += 10 + r1
    if suited:
        score += 2
    if hi - lo <= 1 and not pair:
        score += 3  # connector bonus
    return score


def easy_decision(player, gs):
    to_call = gs["to_call"]
    r = random.random()
    if to_call == 0:
        if r < 0.75:
            return ("check", 0)
        amt = min(player.stack, max(gs["min_raise"], int(gs["pot"] * 0.5) or gs["min_raise"]))
        return ("raise", amt)
    else:
        if to_call >= player.stack:
            return ("call", player.stack) if r < 0.5 else ("fold", 0)
        if r < 0.15:
            return ("fold", 0)
        elif r < 0.85:
            return ("call", to_call)
        else:
            amt = min(player.stack, to_call + max(gs["min_raise"], int(gs["pot"] * 0.5)))
            return ("raise", amt)


def medium_decision(player, gs):
    to_call = gs["to_call"]
    if gs["stage"] == "preflop":
        strength = preflop_strength(player.hole) / 40.0
    else:
        rank = best_hand_rank(player.hole + gs["community"])
        strength = min(1.0, rank[0] / 8.0 + 0.05)

    strength += random.uniform(-0.05, 0.05)
    pot_odds = to_call / (gs["pot"] + to_call) if to_call > 0 else 0

    if to_call == 0:
        if strength > 0.55:
            amt = min(player.stack, max(gs["min_raise"], int(gs["pot"] * 0.6)))
            return ("raise", amt)
        return ("check", 0)
    else:
        if to_call >= player.stack:
            return ("call", player.stack) if strength > 0.5 else ("fold", 0)
        if strength < pot_odds:
            return ("fold", 0)
        elif strength > pot_odds + 0.25:
            amt = min(player.stack, to_call + max(gs["min_raise"], int(gs["pot"] * 0.5)))
            return ("raise", amt)
        else:
            return ("call", to_call)


def hard_decision(player, gs):
    to_call = gs["to_call"]
    trials = 150 if gs["stage"] == "preflop" else 250
    equity = estimate_equity(player.hole, gs["community"], gs["num_active_opponents"], trials)

    if to_call == 0:
        if equity > 0.62:
            amt = min(player.stack, max(gs["min_raise"], int(gs["pot"] * (0.5 + equity * 0.5)) or gs["min_raise"]))
            return ("raise", amt)
        if equity < 0.2 and random.random() < 0.1:
            amt = min(player.stack, max(gs["min_raise"], int(gs["pot"] * 0.6) or gs["min_raise"]))
            return ("raise", amt)  # bluff
        return ("check", 0)
    else:
        pot_odds = to_call / (gs["pot"] + to_call)
        if to_call >= player.stack:
            return ("call", player.stack) if equity > pot_odds else ("fold", 0)
        if equity < pot_odds - 0.05:
            if random.random() < 0.07:
                amt = min(player.stack, to_call + max(gs["min_raise"], int(gs["pot"] * 0.5)))
                return ("raise", amt)  # bluff-raise
            return ("fold", 0)
        elif equity > pot_odds + 0.2:
            amt = min(player.stack, to_call + max(gs["min_raise"], int(gs["pot"] * (0.4 + equity * 0.6))))
            return ("raise", amt)
        else:
            return ("call", to_call)


def normalize_action(p, action, amount, to_call):
    """Clamps/validates any bot's (built-in or player-written) proposed
    action into something the engine can safely apply."""
    if action == "fold":
        return ("fold", 0) if to_call > 0 else ("check", 0)
    if action == "check":
        return ("call", min(to_call, p.stack)) if to_call > 0 else ("check", 0)
    if action == "call":
        return ("call", min(to_call, p.stack))
    if action in ("raise", "all_in"):
        amt = min(amount, p.stack)
        if amt >= p.stack:
            return ("all_in", p.stack)
        if amt <= to_call:
            return ("call", min(to_call, p.stack))
        return ("raise", amt)
    # Unrecognized action from a buggy bot -- default to the safest legal move.
    return ("call", min(to_call, p.stack)) if to_call > 0 else ("check", 0)


def bot_decision(player, gs):
    if player.difficulty == "easy":
        return easy_decision(player, gs)
    elif player.difficulty == "medium":
        return medium_decision(player, gs)
    else:
        return hard_decision(player, gs)


# ---------------------------------------------------------------------------
# Game engine
# ---------------------------------------------------------------------------

def _emit(f, event_type, **fields):
    """Writes one JSON event line to `f` (a writable file, or None to
    no-op). Used so an external renderer (like a game engine) can watch
    a match unfold hand-by-hand, action-by-action, instead of only
    seeing printed text at the end. Never allowed to crash the match."""
    if f is None:
        return
    try:
        rec = {"type": event_type}
        rec.update(fields)
        f.write(json.dumps(rec) + "\n")
        f.flush()
    except Exception:
        pass


class PokerGame:
    def __init__(self, players, small_blind=10, big_blind=20, events_file=None):
        self.players = players
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.dealer_idx = -1
        self.hand_num = 0
        self.pot = 0
        self.community = []
        self.events_file = events_file  # writable file, or None

    def emit(self, event_type, **fields):
        _emit(self.events_file, event_type, **fields)

    # -- seating / rotation helpers -----------------------------------

    def next_active_idx(self, from_idx, predicate):
        n = len(self.players)
        for step in range(1, n + 1):
            cand = (from_idx + step) % n
            if predicate(self.players[cand]):
                return cand
        return None

    def next_dealer(self):
        self.dealer_idx = self.next_active_idx(self.dealer_idx, lambda p: p.stack > 0)
        return self.dealer_idx

    def alive_players(self):
        return [p for p in self.players if p.stack > 0]

    def count_in_hand(self):
        return sum(1 for p in self.players if not p.folded)

    def any_can_still_act(self):
        return sum(1 for p in self.players if p.active) > 1

    def collect(self, p, amount):
        amount = max(0, min(amount, p.stack))
        p.stack -= amount
        p.current_bet += amount
        p.committed += amount
        self.pot += amount
        if p.stack == 0:
            p.all_in = True

    def reset_street_bets(self):
        for p in self.players:
            p.current_bet = 0

    # -- one full hand ----------------------------------------------------

    def play_hand(self):
        for p in self.players:
            p.reset_hand()
            if p.stack <= 0:
                p.folded = True  # busted players sit out; treat as "folded" everywhere
        self.community = []
        self.pot = 0
        deck = make_deck()
        random.shuffle(deck)

        dealer_idx = self.next_dealer()
        sb_idx = self.next_active_idx(dealer_idx, lambda p: p.stack > 0)
        bb_idx = self.next_active_idx(sb_idx, lambda p: p.stack > 0)

        print(f"\n{'=' * 60}")
        print(f"Hand #{self.hand_num}  |  Dealer: {self.players[dealer_idx].name}  "
              f"|  Blinds {self.small_blind}/{self.big_blind}")
        self.emit("hand_start", hand_num=self.hand_num, dealer=self.players[dealer_idx].name,
                   small_blind=self.small_blind, big_blind=self.big_blind,
                   stacks={p.name: p.stack for p in self.players})

        for p in self.players:
            if p.stack > 0:
                p.hole = [deck.pop(), deck.pop()]

        sb_p, bb_p = self.players[sb_idx], self.players[bb_idx]
        self.collect(sb_p, self.small_blind)
        self.collect(bb_p, self.big_blind)
        print(f"{sb_p.name} posts small blind ({sb_p.current_bet})   "
              f"{bb_p.name} posts big blind ({bb_p.current_bet})")
        self.emit("blinds_posted", sb_name=sb_p.name, sb_amount=sb_p.current_bet,
                   bb_name=bb_p.name, bb_amount=bb_p.current_bet, pot=self.pot)

        # Let the renderer know each player's own hole cards -- sent
        # separately per player so a real UI could keep opponents'
        # cards hidden if it wanted to; this reference implementation
        # just sends everyone's for simplicity.
        for p in self.players:
            if p.hole:
                self.emit("hole_cards", player=p.name, hole=p.hole)

        utg_idx = self.next_active_idx(bb_idx, lambda p: p.active)
        if utg_idx is not None:
            self.betting_round(utg_idx, "preflop")

        for stage, num_cards in (("flop", 3), ("turn", 1), ("river", 1)):
            if self.count_in_hand() <= 1:
                break
            self.reset_street_bets()
            self.community += [deck.pop() for _ in range(num_cards)]
            print(f"\n{stage.capitalize()}: {cards_str(self.community)}   Pot: {self.pot}")
            self.emit("street", stage=stage, community=self.community, pot=self.pot)
            if self.any_can_still_act():
                first_idx = self.next_active_idx(dealer_idx, lambda p: p.active)
                if first_idx is not None:
                    self.betting_round(first_idx, stage)

        self.showdown()
        self.print_standings()
        self.emit("hand_end", hand_num=self.hand_num, stacks={p.name: p.stack for p in self.players})

    # -- betting ----------------------------------------------------------

    def betting_round(self, start_idx, stage):
        n = len(self.players)
        order = [(start_idx + step) % n for step in range(n)]
        current_bet = max((p.current_bet for p in self.players if not p.folded), default=0)
        min_raise = self.big_blind

        queue = [i for i in order if self.players[i].active]

        while queue:
            i = queue.pop(0)
            p = self.players[i]
            if p.folded or p.stack == 0:
                continue
            if self.count_in_hand() <= 1:
                return

            to_call = current_bet - p.current_bet
            action, amount = self.get_action(p, to_call, min_raise, stage, current_bet)

            chips_before = p.current_bet
            if action == "fold":
                p.folded = True
            elif action == "check":
                pass
            elif action == "call":
                self.collect(p, min(to_call, p.stack))
            elif action in ("raise", "all_in"):
                self.collect(p, min(amount, p.stack))
                if p.current_bet > current_bet:
                    raise_size = p.current_bet - current_bet
                    current_bet = p.current_bet
                    min_raise = max(min_raise, raise_size)
                    pos = order.index(i)
                    rotated = order[pos + 1:] + order[:pos]
                    queue = [j for j in rotated if self.players[j].active]

            self.emit("action", player=p.name, action=action,
                      chips_added=p.current_bet - chips_before, stage=stage,
                      pot=self.pot, stack_after=p.stack)

    def get_action(self, p, to_call, min_raise, stage, current_bet):
        gs = {
            "community": self.community,
            "pot": self.pot,
            "to_call": to_call,
            "min_raise": min_raise,
            "num_active_opponents": sum(1 for x in self.players if not x.folded and x is not p),
            "stage": stage,
        }
        if p.decision_fn is not None:
            action, amount = self.call_user_bot(p, gs)
        else:
            action, amount = bot_decision(p, gs)
        return normalize_action(p, action, amount, to_call)

    def call_user_bot(self, p, gs):
        """Runs the player-supplied decision function. Never lets a bug in
        that function crash the match -- a broken bot just folds."""
        try:
            result = p.decision_fn(
                list(p.hole), list(gs["community"]), gs["pot"], gs["to_call"],
                gs["min_raise"], p.stack, gs["stage"], gs["num_active_opponents"],
            )
            action, amount = result
            return action, amount
        except Exception as e:
            print(f"  [!] Your bot raised an error ({type(e).__name__}: {e}) -- folding this hand.")
            return "fold", 0

    # -- showdown / side pots ---------------------------------------------

    def build_side_pots(self):
        contributors = [p for p in self.players if p.committed > 0]
        levels = sorted(set(p.committed for p in contributors))
        pots = []
        prev_level = 0
        for level in levels:
            layer_players = [p for p in contributors if p.committed >= level]
            layer_amount = (level - prev_level) * len(layer_players)
            eligible = [p for p in layer_players if not p.folded]
            pots.append((layer_amount, eligible))
            prev_level = level
        return pots

    def showdown(self):
        contenders = [p for p in self.players if not p.folded]

        if len(contenders) == 1:
            winner = contenders[0]
            winner.stack += self.pot
            print(f"\n{winner.name} wins {self.pot} chips (everyone else folded).")
            self.emit("showdown", folded_win=True, winner=winner.name, amount=self.pot, hands=[], pots=[])
            self.pot = 0
            return

        print(f"\n--- Showdown ---   Board: {cards_str(self.community)}")
        ranked = []
        hands_info = []
        for p in contenders:
            r = best_hand_rank(p.hole + self.community)
            ranked.append((p, r))
            desc = hand_description(r)
            hands_info.append({"player": p.name, "hole": p.hole, "description": desc})
            print(f"  {p.name}: {cards_str(p.hole)}  ->  {desc}")

        pots_info = []
        pots = self.build_side_pots()
        for amount, eligible in pots:
            if amount <= 0 or not eligible:
                continue
            eligible_ranked = [(p, r) for p, r in ranked if p in eligible]
            best_r = max(r for _, r in eligible_ranked)
            winners = [p for p, r in eligible_ranked if r == best_r]
            share = amount // len(winners)
            remainder = amount - share * len(winners)
            winner_gains = {}
            for idx, w in enumerate(winners):
                gain = share + (1 if idx < remainder else 0)
                w.stack += gain
                winner_gains[w.name] = gain
                print(f"  {w.name} wins {gain} chips from a {amount}-chip pot ({hand_description(best_r)})")
            pots_info.append({"amount": amount, "winners": winner_gains, "description": hand_description(best_r)})
        self.emit("showdown", folded_win=False, hands=hands_info, pots=pots_info)
        self.pot = 0

    def print_standings(self):
        print("\nStandings:")
        for p in self.players:
            status = "OUT" if p.stack <= 0 else f"{p.stack} chips"
            print(f"  {p.name}: {status}")


# ---------------------------------------------------------------------------
# Running a match against your own bot
# ---------------------------------------------------------------------------

def run_match(user_bot_fn, opponent_difficulty="easy", starting_stack=500,
              small_blind=10, big_blind=20, max_hands=300, events_file=None):
    """Plays a full heads-up match: your bot vs. one built-in bot at the
    given difficulty, until one side is busted (or max_hands is hit)."""
    you = Player("Your Bot", starting_stack, decision_fn=user_bot_fn)
    opp = Player(f"Opponent ({opponent_difficulty.capitalize()})", starting_stack,
                 difficulty=opponent_difficulty)
    game = PokerGame([you, opp], small_blind=small_blind, big_blind=big_blind,
                      events_file=events_file)

    _emit(events_file, "match_start", opponent_tier=opponent_difficulty,
          starting_stack=starting_stack)

    hands = 0
    while True:
        alive = game.alive_players()
        if len(alive) <= 1 or hands >= max_hands:
            break
        game.hand_num += 1
        if game.hand_num > 1 and game.hand_num % 10 == 1:
            game.small_blind = int(game.small_blind * 1.5)
            game.big_blind = game.small_blind * 2
        game.play_hand()
        hands += 1

    if you.stack > opp.stack:
        result = "win"
    elif you.stack < opp.stack:
        result = "loss"
    else:
        result = "draw"

    outcome = {
        "result": result,
        "hands_played": hands,
        "your_stack": you.stack,
        "opponent_stack": opp.stack,
        "opponent_difficulty": opponent_difficulty,
    }
    _emit(events_file, "match_end", **outcome)
    return outcome


# ---------------------------------------------------------------------------
# Difficulty progression (saved to disk so it persists between runs)
# ---------------------------------------------------------------------------

TIERS = ["easy", "medium", "hard"]
WINS_TO_ADVANCE = 3
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poker_progress.json")


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                data = json.load(f)
            if data.get("tier") in TIERS:
                data.setdefault("wins_at_tier", 0)
                data.setdefault("total_wins", 0)
                data.setdefault("total_losses", 0)
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"tier": "easy", "wins_at_tier": 0, "total_wins": 0, "total_losses": 0}


def save_progress(data):
    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        print(f"  [!] Couldn't save progress: {e}")


def play_ranked_match(user_bot_fn, starting_stack=500, state_log_path=None):
    """The main entry point your bot script should call. Plays one match
    against your current opponent tier and updates your saved progress.

    If state_log_path is given, a JSON event is appended to that file
    after every meaningful thing that happens (blinds posted, each
    action, each street, showdown, etc.) so an external renderer (e.g.
    a game engine polling the file) can show the match live instead of
    only seeing the final printed result. A final {"type": "done"}
    event is ALWAYS written, even if your bot code crashes badly --
    that's the renderer's cue to stop watching.
    """
    events_file = None
    try:
        if state_log_path:
            try:
                events_file = open(state_log_path, "w", encoding="utf-8")
            except OSError as e:
                print(f"  [!] Couldn't open state log file: {e}")

        progress = load_progress()
        tier = progress["tier"]

        print(f"{'=' * 60}")
        print(f"RANKED MATCH -- opponent tier: {tier.upper()}")
        if tier != TIERS[-1]:
            print(f"({progress['wins_at_tier']}/{WINS_TO_ADVANCE} wins to reach "
                  f"{TIERS[TIERS.index(tier) + 1].upper()})")
        else:
            print("(you've reached the highest tier)")
        print(f"Career record: {progress['total_wins']}W - {progress['total_losses']}L")
        print(f"{'=' * 60}")
        _emit(events_file, "ranked_start", tier=tier, wins_at_tier=progress["wins_at_tier"],
              wins_to_advance=WINS_TO_ADVANCE, total_wins=progress["total_wins"],
              total_losses=progress["total_losses"], starting_stack=starting_stack)

        outcome = run_match(user_bot_fn, opponent_difficulty=tier,
                             starting_stack=starting_stack, events_file=events_file)

        print(f"\n{'=' * 60}")
        print(f"MATCH RESULT: {outcome['result'].upper()}")
        print(f"Hands played: {outcome['hands_played']}   "
              f"Your stack: {outcome['your_stack']}   Opponent stack: {outcome['opponent_stack']}")

        leveled_up = False
        next_tier = None
        if outcome["result"] == "win":
            progress["total_wins"] += 1
            progress["wins_at_tier"] += 1
            if progress["wins_at_tier"] >= WINS_TO_ADVANCE and tier != TIERS[-1]:
                next_tier = TIERS[TIERS.index(tier) + 1]
                progress["tier"] = next_tier
                progress["wins_at_tier"] = 0
                leveled_up = True
                print(f"\n*** LEVEL UP! Your next match will be against a {next_tier.upper()} opponent. ***")
            elif tier != TIERS[-1]:
                remaining = WINS_TO_ADVANCE - progress["wins_at_tier"]
                nxt = TIERS[TIERS.index(tier) + 1]
                print(f"\nWin {remaining} more to face a {nxt.upper()} opponent.")
            else:
                print("\nYou beat the hardest bot. Well played.")
        elif outcome["result"] == "loss":
            progress["total_losses"] += 1
            print("\nTough beat -- refine your bot's strategy and try again.")
        else:
            print("\nIt's a draw -- no tier change.")

        print(f"{'=' * 60}")
        save_progress(progress)
        _emit(events_file, "ranked_end", result=outcome["result"], leveled_up=leveled_up,
              new_tier=progress["tier"], next_tier=next_tier,
              wins_at_tier=progress["wins_at_tier"], wins_to_advance=WINS_TO_ADVANCE,
              total_wins=progress["total_wins"], total_losses=progress["total_losses"])
        return outcome
    except Exception as e:
        _emit(events_file, "fatal_error", message=f"{type(e).__name__}: {e}")
        raise
    finally:
        _emit(events_file, "done")
        if events_file:
            try:
                events_file.close()
            except OSError:
                pass
