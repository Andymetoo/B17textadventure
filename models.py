"""JSON-safe campaign data. Each aircraft flies with its regular ten-person crew."""
import random
import secrets

SCHEMA_VERSION = 1
CAMPAIGN_LENGTH = 12
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
        captain = f"Replacement crew {index + 1}-{replacement}"
        skill, condition, fatigue = .65, 100, 0
    return {"id": f"a{index + 1}", "name": name, "captain": captain,
            "trait": trait, "skill": skill, "condition": condition,
            "fatigue": fatigue, "sorties": 0, "lost": False,
            "job": None, "replacement": replacement}


def new_campaign(seed=None):
    seed = secrets.randbelow(2 ** 31) if seed is None else seed
    return {"schema": SCHEMA_VERSION, "seed": seed, "revision": 0,
            "operation": 1, "length": CAMPAIGN_LENGTH, "score": 0,
            "supplies": 18, "parts": 8, "losses": 0,
            "aircraft": [new_aircraft(i) for i in range(6)],
            "active": None, "debriefs": [], "messages": [],
            "clock_offset": 0, "completed": False}


def briefing(state):
    """Stable offers: waiting or refreshing never changes the next briefing."""
    rng = random.Random(f"{state['seed']}:briefing:{state['operation']}")
    weather = rng.choice(["Clear", "Broken cloud", "Overcast"])
    industry = ["Rail marshalling yard", "Engine assembly works", "Coastal repair docks",
                "Aircraft components plant", "River freight junction", "Fuel distribution depot"]
    support = ["Forward supply depot", "Coastal transport sidings", "Vehicle repair works"]
    late = state['operation'] > 6
    return [
        {"id": "priority", "name": rng.choice(industry), "type": "Priority objective",
         "description": "A valuable target with heavier defenses. A strong formation earns substantial campaign progress.",
         "weather": weather, "risk": .43 if late else .36,
         "required": 2.55 if late else 2.25, "reward": 9,
         "cost": 2, "hours": 3, "bonus": "none"},
        {"id": "support", "name": rng.choice(support), "type": "Supporting operation",
         "description": "A shorter assignment. Effective bombing secures an extra allocation for this detachment.",
         "weather": weather, "risk": .23, "required": 1.65,
         "reward": 4, "cost": 1, "hours": 2,
         "bonus": rng.choice(["supplies", "parts"])},
    ]
