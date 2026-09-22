"""JSON-safe campaign data. Each aircraft flies with its regular ten-person crew."""
import secrets

from content import TOUR_GOALS, TOUR_LENGTHS, build_briefing

SCHEMA_VERSION = 2
CAMPAIGN_LENGTH = 21
MAX_AIRCRAFT = 8
ROSTER = [
    ("Lucky Penny", "Reynolds", "steady", .86, 100, 22),
    ("Belle of the Blue", "Morgan", "precision", .81, 94, 10),
    ("Second Helping", "Kowalski", "navigator", .78, 88, 0),
    ("Sunday Punch", "Halloway", "steady", .73, 100, 48),
    ("Paper Moon", "Valenti", "navigator", .76, 62, 12),
    ("Old Reliable", "Miller", "precision", .89, 78, 60),
    ("Extra Trouble", "Brooks", "steady", .66, 100, 0),
    ("Borrowed Time", "Ellis", "navigator", .66, 100, 0),
]
TRAITS = {
    "steady": "Steady hands · less damage from enemy action",
    "precision": "Bombing specialist · stronger target effect",
    "navigator": "Weather reader · smaller visibility penalty",
}


def new_aircraft(index, replacement=0):
    name, captain, trait, skill, condition, fatigue = ROSTER[index]
    if replacement:
        name = f"{name} II" if replacement == 1 else f"{name} {replacement + 1}"
        captain = ("Preston", "Collins", "Webb", "Adams", "Carter", "Hughes", "Fuller", "Grant", "Dawson", "Price", "Bennett", "Hayes", "Turner", "Ward", "Foster", "Blake")[(index + 8 * (replacement - 1)) % 16]
        skill, condition, fatigue = .65, 100, 0
    return {"id": f"a{index + 1}", "name": name, "captain": captain,
            "trait": trait, "skill": skill, "condition": condition,
            "fatigue": fatigue, "sorties": 0, "lost": False,
            "job": None, "replacement": replacement, "history": [], "milestones": [],
            "unavailable_until": 0, "leave_reason": "", "away_until": None, "crew_fate": "safe"}


def new_campaign(seed=None, length=CAMPAIGN_LENGTH):
    if length not in TOUR_LENGTHS:
        raise ValueError("Choose a 7-, 14-, 21-, or 28-operation tour.")
    seed = secrets.randbelow(2 ** 31) if seed is None else seed
    return {"schema": SCHEMA_VERSION, "seed": seed, "revision": 0,
            "operation": 1, "length": length, "goal": TOUR_GOALS[length], "score": 0,
            "supplies": 18, "parts": 8, "losses": 0,
            "aircraft": [new_aircraft(i) for i in range(6)],
            "active": None, "debriefs": [], "messages": [],
            "clock_offset": 0, "completed": False, "effects": {}, "opportunity": None,
            "decision": None, "decision_history": [], "journal": []}


def briefing(state):
    return build_briefing(state)


def migrate_campaign(state):
    """Upgrade existing saves in place; retain 12-operation tours and v1 flights."""
    if state.get("schema") == SCHEMA_VERSION:
        return
    if state.get("schema") != 1:
        raise ValueError("This save uses an unsupported version. Preserve the database before upgrading.")
    state.update(schema=SCHEMA_VERSION, goal=state["length"] * 5, effects={},
                 opportunity=None, decision=None, decision_history=[], journal=[])
    defaults = {"history": [], "milestones": [], "unavailable_until": 0,
                "leave_reason": "", "away_until": None, "crew_fate": "safe"}
    import copy
    for plane in state["aircraft"]:
        for key, value in defaults.items():
            plane.setdefault(key, copy.deepcopy(value))
        if plane["lost"]:
            plane["crew_fate"] = "missing"
    # Old mission snapshots and RNG paths are deliberately left intact. Their
    # resolver finishes the dispatched operation under its original rules.
    if state["active"]:
        state["active"].setdefault("rules_version", 1)
