"""Reference bots.

Every bot is a function `act(state) -> action` that returns one of the strings in
poker.action: "fold", "check", "call", or "raise". The engine sanitizes anything
illegal, but well-behaved bots should only return actions in `state.legal_actions`.
"""

import random

from poker.action import CALL, CHECK, FOLD, RAISE
from poker.evaluator import evaluate
from poker.state import GameState

# Dedicated RNG so random_bot is reproducible regardless of the match seed.
_rng = random.Random(0)


def folder(state: GameState) -> str:
    """Folds whenever facing a bet, otherwise checks. The 'do nothing' baseline."""
    return CHECK if state.to_call == 0 else FOLD


def caller(state: GameState) -> str:
    """Calls/checks everything to showdown. Never folds, never raises."""
    return CHECK if CHECK in state.legal_actions else CALL


def random_bot(state: GameState) -> str:
    """Picks uniformly among the currently legal actions."""
    return _rng.choice(state.legal_actions)


def tight_aggressive(state: GameState) -> str:
    """A simple value bot: raise strong hands, call playable ones, fold the rest.

    Demonstrates using the evaluator on `state` to gauge hand strength.
    """
    if state.street == "preflop":
        r1, r2 = sorted((c.rank for c in state.hole_cards), reverse=True)
        suited = state.hole_cards[0].suit == state.hole_cards[1].suit
        pair = r1 == r2
        strong = pair and r1 >= 9            # 99+
        playable = (
            pair                              # any pair
            or (r1 >= 10 and r2>=6)        # K10+/AQ etc.
            or (suited and r1 >= 5)
        )
        if strong and RAISE in state.legal_actions:
            return RAISE
        if playable:
            return CHECK if state.to_call == 0 else CALL
        return CHECK if state.to_call == 0 else FOLD

    # Postflop: evaluate the best 5-card hand and act on its category.
    category = evaluate(state.hole_cards + state.community_cards)[0]
    if category >= 2 and RAISE in state.legal_actions:   # two pair or better
        return RAISE
    if category >= 1:                                    # at least a pair
        return CHECK if state.to_call == 0 else CALL
    return CHECK if state.to_call == 0 else FOLD


def maniac(state: GameState) -> str:
    """Pure aggression: raise whenever possible, otherwise call. Never folds.

    A useful punching bag/stress test -- shows how an over-aggressive style bleeds
    chips against bots that fold weak hands and value-bet strong ones.
    """
    if RAISE in state.legal_actions:
        return RAISE
    return CHECK if CHECK in state.legal_actions else CALL


def rock(state: GameState) -> str:
    """Ultra-tight 'nit': only puts chips in with premium/strong hands, else folds.

    Tighter than tight_aggressive -- it folds anything mediocre, so it wins small
    pots and loses the blinds while waiting for monsters.
    """
    if state.street == "preflop":
        r1, r2 = sorted((c.rank for c in state.hole_cards), reverse=True)
        premium = (r1 == r2 and r1 >= 11) or (r1 == 14 and r2 >= 13)  # QQ+ or AK
        if premium and RAISE in state.legal_actions:
            return RAISE
        if premium:
            return CALL
        return CHECK if state.to_call == 0 else FOLD

    category = evaluate(state.hole_cards + state.community_cards)[0]
    if category >= 3 and RAISE in state.legal_actions:   # trips or better
        return RAISE
    if category >= 2:                                    # two pair: just call
        return CHECK if state.to_call == 0 else CALL
    return CHECK if state.to_call == 0 else FOLD


def pot_odds_caller(state: GameState) -> str:
    """Never raises; calls only when the pot offers good enough odds for its hand.

    Demonstrates the pot-odds idea: compare the price to call (`to_call / (pot +
    to_call)`) against a rough estimate of hand strength. Folds when the price is
    worse than the hand justifies.
    """
    if state.to_call == 0:
        return CHECK

    # Rough hand-strength estimate in [0, 1].
    if state.street == "preflop":
        r1, r2 = sorted((c.rank for c in state.hole_cards), reverse=True)
        strength = (r1 + r2) / 28.0
        if r1 == r2:
            strength += 0.25
    else:
        category = evaluate(state.hole_cards + state.community_cards)[0]
        strength = category / 8.0

    price = state.to_call / (state.pot + state.to_call)
    return CALL if strength >= price else FOLD


def position_aware(state: GameState) -> str:
    """Plays more hands aggressively in late position, tighter in early position.

    Demonstrates using `my_seat`, `button`, and `num_players` to gauge position.
    Distance from the button (in seats yet to act) is a key poker concept.
    """
    # 0 = on the button (best), larger = earlier position (worse).
    seats_after = (state.button - state.my_seat) % state.num_players
    late = seats_after <= 1                                # button or cutoff

    if state.street == "preflop":
        r1, r2 = sorted((c.rank for c in state.hole_cards), reverse=True)
        pair = r1 == r2
        threshold = 18 if late else 23                    # looser when in position
        playable = pair or (r1 + r2) >= threshold
        if pair and r1 >= 10 and RAISE in state.legal_actions:
            return RAISE
        if playable:
            return CHECK if state.to_call == 0 else CALL
        return CHECK if state.to_call == 0 else FOLD

    category = evaluate(state.hole_cards + state.community_cards)[0]
    if category >= 2 and RAISE in state.legal_actions:
        return RAISE
    if category >= 1:
        return CHECK if state.to_call == 0 else CALL
    # In late position, take a free card; otherwise give up.
    return CHECK if state.to_call == 0 else FOLD
