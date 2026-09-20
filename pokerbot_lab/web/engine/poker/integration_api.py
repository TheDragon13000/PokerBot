"""Versioned JSON boundary for embedding Bet2Bot in another application.

Unlike ``game_api`` (a Python-friendly API used by Pyodide), this module accepts and
returns JSON strings. That makes it a stable seam for Godot, subprocesses, WebViews,
and contract tests without exposing Python objects across the boundary.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from poker.action import ACTIONS
from poker.game_api import OPPONENTS, run_level
from poker.strategy import TIERS, all_hand_classes

PROTOCOL = "bet2bot-godot/v1"
POLICY_SCHEMA_VERSION = 1
_MAX_HANDS = 2_000
_MAX_CAPTURE = 10
_STREETS = ("flop", "turn", "river")


def _error(code: str, message: str, field: Optional[str] = None) -> dict:
    error = {"code": code, "message": message}
    if field is not None:
        error["field"] = field
    return {"protocol": PROTOCOL, "ok": False, "error": error}


def describe() -> dict:
    """Describe the integration contract and stable engine identifiers."""
    return {
        "protocol": PROTOCOL,
        "ok": True,
        "result": {
            "policySchemaVersion": POLICY_SCHEMA_VERSION,
            "opponents": sorted(OPPONENTS),
            "actions": list(ACTIONS),
            "streets": list(_STREETS),
            "formats": ["limit", "no_limit"],
            "maxHands": _MAX_HANDS,
            "maxCapture": _MAX_CAPTURE,
        },
    }


def validate_strategy(policy: Any) -> dict:
    """Validate the portable strategy policy consumed by ``StrategyBot``.

    The current policy is intentionally simple: a complete 169-class preflop map,
    then three street policies containing ordered rules and a default action.
    Unknown condition keys are tolerated so the contract can grow without forcing
    old hosts to understand every builder feature.
    """
    if not isinstance(policy, dict):
        return _error("INVALID_POLICY", "Strategy must be an object.", "strategy")
    version = policy.get("schemaVersion", POLICY_SCHEMA_VERSION)
    if version != POLICY_SCHEMA_VERSION:
        return _error(
            "UNSUPPORTED_POLICY_VERSION",
            f"Expected policy schema {POLICY_SCHEMA_VERSION}, got {version!r}.",
            "strategy.schemaVersion",
        )

    preflop = policy.get("preflop")
    if not isinstance(preflop, dict):
        return _error("INVALID_POLICY", "Preflop must be an object.", "strategy.preflop")
    required = set(all_hand_classes())
    missing = sorted(required - set(preflop))
    if missing:
        return _error(
            "INVALID_POLICY",
            f"Preflop is missing {len(missing)} hand classes (first: {missing[0]}).",
            "strategy.preflop",
        )
    for hand in required:
        if preflop[hand] not in ACTIONS:
            return _error(
                "INVALID_POLICY",
                f"Unknown action {preflop[hand]!r} for {hand}.",
                f"strategy.preflop.{hand}",
            )

    for street in _STREETS:
        value = policy.get(street)
        if not isinstance(value, dict):
            return _error("INVALID_POLICY", f"{street} must be an object.", f"strategy.{street}")
        if value.get("default") not in ACTIONS:
            return _error(
                "INVALID_POLICY",
                f"{street} needs a valid default action.",
                f"strategy.{street}.default",
            )
        rules = value.get("rules")
        if not isinstance(rules, list):
            return _error("INVALID_POLICY", f"{street}.rules must be an array.", f"strategy.{street}.rules")
        for index, rule in enumerate(rules):
            field = f"strategy.{street}.rules.{index}"
            if not isinstance(rule, dict) or not isinstance(rule.get("when", {}), dict):
                return _error("INVALID_POLICY", "Each rule must contain a condition object.", field)
            if rule.get("action") not in ACTIONS:
                return _error("INVALID_POLICY", "Each rule needs a valid action.", f"{field}.action")
            tier = rule.get("when", {}).get("handTier")
            if tier is not None and tier not in TIERS:
                return _error("INVALID_POLICY", f"Unknown hand tier {tier!r}.", f"{field}.when.handTier")

    # Return the normalized engine policy without the contract-only version field.
    normalized = {k: v for k, v in policy.items() if k != "schemaVersion"}
    return {"protocol": PROTOCOL, "ok": True, "result": {"strategy": normalized}}


def _validate_run(payload: Any) -> Tuple[Optional[dict], Optional[dict]]:
    if not isinstance(payload, dict):
        return None, _error("INVALID_REQUEST", "Run payload must be an object.", "payload")

    checked = validate_strategy(payload.get("strategy"))
    if not checked["ok"]:
        return None, checked

    opponents = payload.get("opponents", ["caller"])
    if isinstance(opponents, str):
        opponents = [opponents]
    if not isinstance(opponents, list) or not opponents:
        return None, _error("INVALID_REQUEST", "At least one opponent is required.", "payload.opponents")
    unknown = [name for name in opponents if name not in OPPONENTS]
    if unknown:
        return None, _error("UNKNOWN_OPPONENT", f"Unknown opponent: {unknown[0]!r}.", "payload.opponents")

    hands = payload.get("hands", 100)
    capture = payload.get("capture", 2)
    if not isinstance(hands, int) or isinstance(hands, bool) or not 1 <= hands <= _MAX_HANDS:
        return None, _error("INVALID_REQUEST", f"hands must be 1..{_MAX_HANDS}.", "payload.hands")
    if not isinstance(capture, int) or isinstance(capture, bool) or not 0 <= capture <= _MAX_CAPTURE:
        return None, _error("INVALID_REQUEST", f"capture must be 0..{_MAX_CAPTURE}.", "payload.capture")

    seed = payload.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        return None, _error("INVALID_REQUEST", "seed must be an integer or null.", "payload.seed")

    config = payload.get("config", {"betting": "limit"})
    if not isinstance(config, dict):
        return None, _error("INVALID_REQUEST", "config must be an object.", "payload.config")
    allowed = {"small_bet", "big_bet", "small_blind", "big_blind", "raise_cap", "betting", "stack"}
    unknown_config = sorted(set(config) - allowed)
    if unknown_config:
        return None, _error("INVALID_REQUEST", f"Unknown config field {unknown_config[0]!r}.", "payload.config")
    if config.get("betting", "limit") not in ("limit", "no_limit"):
        return None, _error("INVALID_REQUEST", "betting must be 'limit' or 'no_limit'.", "payload.config.betting")

    return {
        "strategy": checked["result"]["strategy"],
        "opponents": opponents,
        "hands": hands,
        "seed": seed,
        "capture": capture,
        "config": config,
    }, None


def run_match(payload: Any) -> dict:
    """Validate and run a bounded match, returning integration-shaped results."""
    request, error = _validate_run(payload)
    if error is not None:
        return error
    assert request is not None

    result = run_level(
        opponent=request["opponents"],
        strategy=request["strategy"],
        hands=request["hands"],
        seed=request["seed"],
        capture=request["capture"],
        config=request["config"],
    )
    if result.get("error"):
        return _error("ENGINE_ERROR", result["error"])

    return {
        "protocol": PROTOCOL,
        "ok": True,
        "result": {
            "playerNet": result["player_net"],
            "playerBb100": result["player_bb100"],
            "hands": result["hands"],
            "bigBlind": result["big_blind"],
            "players": result["players"],
            "summary": result["summary"],
            "timeline": result["timeline"],
            "replays": result["replays"],
        },
    }


def handle(request: Any) -> dict:
    """Dispatch one decoded request envelope."""
    if not isinstance(request, dict):
        return _error("INVALID_REQUEST", "Request must be an object.")
    request_id = request.get("id")
    if request.get("protocol") != PROTOCOL:
        response = _error("UNSUPPORTED_PROTOCOL", f"Expected protocol {PROTOCOL!r}.", "protocol")
    elif request.get("type") == "describe":
        response = describe()
    elif request.get("type") == "validate_strategy":
        response = validate_strategy(request.get("payload", {}).get("strategy"))
    elif request.get("type") == "run_match":
        response = run_match(request.get("payload"))
    else:
        response = _error("UNKNOWN_REQUEST", f"Unknown request type {request.get('type')!r}.", "type")
    if request_id is not None:
        response["id"] = request_id
    return response


def handle_json(raw: str) -> str:
    """JSON-in / JSON-out entry point; never leaks a traceback across the boundary."""
    try:
        request = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return json.dumps(_error("INVALID_JSON", "Request is not valid JSON."), separators=(",", ":"))
    try:
        response = handle(request)
    except Exception:
        response = _error("ENGINE_ERROR", "The poker engine could not complete the request.")
    return json.dumps(response, separators=(",", ":"))


def main() -> int:
    """One-shot stdio transport: read one JSON request, print one JSON response."""
    import sys

    raw = sys.stdin.read()
    sys.stdout.write(handle_json(raw))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
