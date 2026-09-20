"""Actions a bot can take, plus parsing, legality checking, and sanitizing.

Bots return one of the four action verbs below. In *Limit* games a raise has a fixed
size, so the verb alone is enough. In *No-Limit* games a raise may carry an amount —
the TOTAL number of chips the actor wants committed this street ("raise TO X"):

    "raise"            -> the engine picks a default size (a pot-sized raise)
    "raise:12"         -> raise to 12 chips this street
    ("raise", 12)      -> same, as a tuple (also accepts lists)

Amounts are clamped by the engine to the legal window [min_raise_to, max_raise_to]
(max is an all-in), so a bot can never raise an illegal amount — only an illegal
*verb* counts as a mistake.
"""

from typing import List, Optional, Tuple

FOLD = "fold"
CHECK = "check"
CALL = "call"
RAISE = "raise"

ACTIONS = (FOLD, CHECK, CALL, RAISE)


def parse_action(raw: object) -> Tuple[Optional[str], Optional[int]]:
    """Split any bot return value into (verb, amount) — (None, None) if unrecognisable.

    Accepts "raise", "raise:12", "raise 12", ("raise", 12), ["raise", 12], and the
    plain verbs. Verbs are case-insensitive; amounts must be int-like.
    """
    if isinstance(raw, (tuple, list)) and raw:
        verb = raw[0]
        amount = raw[1] if len(raw) > 1 else None
        if isinstance(verb, str):
            verb = verb.strip().lower()
            if verb in ACTIONS:
                try:
                    return verb, (None if amount is None else int(amount))
                except (TypeError, ValueError):
                    return verb, None
        return None, None

    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in ACTIONS:
            return text, None
        for sep in (":", " "):
            if sep in text:
                verb, _, tail = text.partition(sep)
                verb = verb.strip()
                if verb in ACTIONS:
                    try:
                        return verb, int(tail.strip())
                    except ValueError:
                        return verb, None
        return None, None

    return None, None


def legal_actions(
    to_call: int,
    raises_so_far: int,
    raise_cap: int,
    stack: Optional[int] = None,
    betting: str = "limit",
) -> List[str]:
    """Return the action verbs that are legal in the current spot.

    - Facing a bet (to_call > 0): FOLD or CALL (a short stack calls all-in for less).
    - No bet (to_call == 0): CHECK.
    - RAISE requires chips beyond the call (stack > to_call, when stacks apply) and,
      in Limit only, that the per-street raise cap has not been reached.
    """
    actions: List[str] = []
    if to_call > 0:
        actions.append(FOLD)
        actions.append(CALL)
    else:
        actions.append(CHECK)

    can_raise = stack is None or stack > to_call
    if betting == "limit" and raises_so_far >= raise_cap:
        can_raise = False
    if can_raise:
        actions.append(RAISE)
    return actions


def sanitize(action: object, legal: List[str]) -> str:
    """Map any bot return value to a safe, legal action VERB (amounts are handled —
    clamped — by the engine).

      - RAISE when not allowed   -> CALL if facing a bet, else CHECK
      - FOLD when checking free  -> CHECK (never fold for free)
      - garbage / illegal / None -> CALL if facing a bet, else CHECK (FOLD last)
    """
    verb, _ = parse_action(action)

    if verb in legal:
        # Never fold when checking is free -- treat it as a check.
        if verb == FOLD and CHECK in legal:
            return CHECK
        return verb

    # Illegal or unrecognised: choose the safest legal fallback.
    if verb == RAISE and CALL in legal:
        return CALL
    if CALL in legal:
        return CALL
    if CHECK in legal:
        return CHECK
    return FOLD


def is_legal(action: object, legal: List[str]) -> bool:
    """True if `action`'s verb is one of the legal action verbs."""
    verb, _ = parse_action(action)
    return verb is not None and verb in legal
