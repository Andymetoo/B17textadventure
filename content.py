"""Authored campaign situations and reports; randomness is seeded by operation.

No text invents an outcome: callers select passages after applying the matching
rule. Costs and lasting effects are part of the same definition as each choice.
"""
import random

TOUR_LENGTHS = (7, 14, 21, 28)
TOUR_GOALS = {7: 35, 14: 65, 21: 95, 28: 125}

TARGETS = {
    "rail": {
        "names": ("Saint-Omer freight junction", "Amiens marshalling yard", "Lille east sidings"),
        "brief": "Loaded wagons are collecting behind the junction. Break the lines and we may catch the shipment's destination before it disperses.",
        "consequence": "At 65% target effect, opens an industrial follow-up for the next two operations.",
        "effect": "followup", "reward": 8, "required": 2.15, "risk": .30,
    },
    "industry": {
        "names": ("Northern engine works", "Riverside assembly halls", "Inland aircraft components plant"),
        "brief": "Intelligence has identified the assembly buildings. This is a precise job: scattered bombs will leave much of the machinery working.",
        "consequence": "High campaign value. Bombing specialists are particularly useful here.",
        "effect": "precision", "reward": 10, "required": 2.55, "risk": .36,
    },
    "airfield": {
        "names": ("Forward fighter dispersal field", "Coastal interceptor base", "Southern maintenance airfield"),
        "brief": "The interceptors troubling our routes are being serviced here. Hitting their workshops could give the next formations some breathing room.",
        "consequence": "At 65% target effect, reduces enemy exposure for the next two operations.",
        "effect": "disruption", "reward": 7, "required": 2.10, "risk": .34,
    },
    "harbor": {
        "names": ("Channel repair docks", "Estuary loading basin", "Outer harbor workshops"),
        "brief": "The docks are busy and well defended. Command will release engineering stores if we can put their repair facilities out of action.",
        "consequence": "Up to 2 extra parts, scaled by target effect, as well as campaign progress.",
        "effect": "parts", "reward": 8, "required": 2.35, "risk": .33,
    },
    "supply": {
        "names": ("Coastal transport sidings", "Forward supply depot", "Road-and-rail transfer station"),
        "brief": "A shorter route and a broad target. Command can redirect additional flight allocations to us if this assignment succeeds.",
        "consequence": "Up to 6 extra supplies, scaled by target effect.",
        "effect": "supplies", "reward": 4, "required": 1.60, "risk": .21,
    },
    "workshop": {
        "names": ("Vehicle overhaul depot", "Field repair workshops", "Canal-side maintenance stores"),
        "brief": "Engineering command wants these workshops quiet. Do the job and our requisition for replacement components moves up the list.",
        "consequence": "Up to 4 extra parts, scaled by target effect.",
        "effect": "parts", "reward": 4, "required": 1.60, "risk": .22,
    },
    "recon": {
        "names": ("Coastal photographic sweep", "Inland route reconnaissance", "River crossing survey"),
        "brief": "Bring back usable photographs of the approaches and defenses. There is no bomb load; clear navigation and a steady camera run matter.",
        "consequence": "At 65% coverage, improves mission accuracy for the next two operations.",
        "effect": "intel", "reward": 4, "required": 1.45, "risk": .19,
    },
}


def chapter(state):
    operation, length = state["operation"], state["length"]
    if operation <= 2:
        return {"name": "Finding our feet", "text": "Shorter reaches, familiar routes. Learn which crews you trust before the demands grow.", "risk": -.11}
    if operation <= max(3, round(length * .45)):
        return {"name": "The work builds", "text": "The easy assignments are thinning out. What you keep in reserve now will shape the harder days.", "risk": 0}
    if operation <= round(length * .8):
        return {"name": "A changing sky", "text": "Damage, experience, and unfinished business are accumulating. There is no perfect formation for every job.", "risk": .035}
    return {"name": "The last stretch", "text": "The end of the tour is in sight. Every crew has a history now; decide which risks are still worth taking.", "risk": .055}


def build_briefing(state):
    op = state["operation"]
    rng = random.Random(f"{state['seed']}:offers-v2:{op}")
    weather = rng.choice(["Clear", "Broken cloud"] if op <= 2 else ["Clear", "Broken cloud", "Overcast"])
    # Rotate the main assignment so refreshes and resource spending cannot reroll it.
    cycle = ["rail", "industry", "airfield", "harbor"]
    random.Random(f"{state['seed']}:target-order").shuffle(cycle)
    primary = cycle[(op - 1) % len(cycle)]
    support = rng.choice(["supply", "workshop"] if op <= 2 else ["supply", "workshop", "recon"])
    effects = state.get("effects", {})
    disruption = effects.get("disruption", 0) >= op
    intelligence = effects.get("intel", 0) >= op
    offers = []
    for mid, kind in [("priority", primary), ("support", support)]:
        spec = TARGETS[kind]
        main = mid == "priority"
        consequence = spec["consequence"]
        remaining = min(2, state["length"] - op)
        if spec["effect"] in ("intel", "disruption", "followup"):
            if remaining == 0:
                consequence = "Final operation: no later sortie in this tour can use the follow-on advantage."
            elif remaining == 1:
                consequence = consequence.replace("next two operations", "final operation")
        risk = max(.08, spec["risk"] + chapter(state)["risk"] - (.09 if disruption else 0))
        offers.append({"id": mid, "kind": kind, "name": rng.choice(spec["names"]),
            "type": "Priority objective" if main else "Supporting operation",
            "description": spec["brief"], "consequence": consequence,
            "weather": weather, "risk": risk, "required": spec["required"] - (.25 if op <= 2 else 0),
            "reward": spec["reward"], "cost": 2 if main else 1, "hours": 3 if main else 2,
            "bonus": spec["effect"] if spec["effect"] in ("supplies", "parts") else "none",
            "bonus_max": (2 if main else 4) if spec["effect"] == "parts" else 6,
            "effect": spec["effect"], "intel": intelligence, "disruption": disruption,
            "opening": op <= 2, "defenses": "Light" if risk < .20 else ("Moderate" if risk < .32 else "Heavy")})
    opportunity = state.get("opportunity")
    if opportunity and opportunity["opens"] <= op <= opportunity["expires"]:
        offers.append({"id": "followup", "kind": "industry", "name": opportunity["target"],
            "type": "Follow-up opportunity", "description": opportunity["description"],
            "consequence": "A known shipment makes this a valuable, more accessible industrial target. Available through operation " + str(opportunity["expires"]) + ".",
            "weather": weather, "risk": max(.10, .27 + chapter(state)["risk"] - (.09 if disruption else 0)),
            "required": 2.0, "reward": 9, "cost": 2, "hours": 3,
            "bonus": "none", "bonus_max": 0, "effect": "precision", "intel": True,
            "disruption": disruption, "opening": False, "defenses": "Moderate"})
    return offers


OUTBOUND_EVENTS = (
    {"id": "clear", "text": "The coast fell behind without a shot. {captain} checked the formation and settled into the climb.", "damage": 0},
    {"id": "flak", "text": "A flak burst punched fragments through {name}. The crew isolated the damage and reported {damage} condition lost.", "damage": 1},
    {"id": "fighters", "text": "Fighters made two passes at {name}. The gunners kept their stations; the aircraft took {damage} condition damage.", "damage": 1},
    {"id": "engine", "text": "Oil pressure fell on the climb. {captain} feathered the engine and brought {name} back before reaching the coast.", "abort": True, "damage": 12},
    {"id": "oxygen", "text": "An oxygen feed failed at altitude. {captain} descended and turned for home; the crew needs a medical check before its next sortie.", "abort": True, "medical": True, "damage": 4},
    {"id": "separation", "text": "Cloud split the formation. The navigator found the rendezvous, but the detour left everyone more tired than planned.", "fatigue": 8, "damage": 0},
)

TARGET_EVENTS = (
    {"id": "on_target", "factor": 1.0, "text": "{name} made a steady run. The observer reported strikes within the assigned area."},
    {"id": "cloud_gap", "factor": 1.16, "text": "A gap opened in the cloud at just the right moment. The bombardier had a clear view and made it count."},
    {"id": "secondary", "factor": .55, "text": "The assigned aiming point stayed hidden. The captain used the briefed secondary target; the result counts, but the main objective remains partly intact."},
    {"id": "hung_bombs", "factor": .30, "text": "Part of the bomb load failed to release. The crew made the aircraft safe and headed home; only a fraction of the planned strike reached the target."},
    {"id": "scattered", "factor": .72, "text": "The run broke up under fire. The observer saw scattered impacts beyond the intended buildings."},
    {"id": "excellent", "factor": 1.20, "text": "The bombardier called a clean line through the aiming point. The returning photographs should tell a good story."},
)

HOME_LINES = (
    "{captain} waited until all ten were off the aircraft before signing the return sheet.",
    "The crew chief listened to {captain}'s list, then called for the tool trolley. Another aircraft home; another job for the night shift.",
    "Boots hit the hardstand. Someone asked about tea before anyone asked about the score.",
    "{captain} brought the debrief sheet in folded twice. The navigator had drawn the difficult part of the route on the back.",
    "The ground crew counted the men as they climbed out of {name}. Then they began counting the holes.",
)

MILESTONES = {
    3: "Three sorties home. The ground crew now recognizes their approach before anyone reads the tail number.",
    6: "Six returns. New crews have started listening when this captain talks through a route.",
    12: "Twelve returns. The crew's names have become part of the airfield's daily vocabulary.",
    20: "Twenty returns. There is a quiet space at the briefing table that everyone leaves for them.",
}


def ground_situation(state):
    """One optional, operation-bound decision, selected from eligible situations."""
    op = state["operation"]
    if op <= 2 or state["completed"]:
        return None
    rng = random.Random(f"{state['seed']}:ground:{op}")
    if rng.random() > .72:
        return None
    usable = [p for p in state["aircraft"] if not p["lost"] and not p.get("away_until") and not p.get("job") and p.get("unavailable_until", 0) <= op]
    candidates = [
        {"kind": "parts_trade", "title": "A lorry with the wrong manifest", "speaker": "Chief mechanic",
         "text": "The neighboring field has spare components but is short of flight allocations. Their quartermaster is willing to exchange stores before the next dispatch.",
         "choice": "Make the exchange", "cost": {"supplies": 3}, "gain": {"parts": 2}, "detail": "Spend 3 supplies; receive 2 parts.", "result": "The lorry leaves lighter and our parts shelves look healthier."},
        {"kind": "fuel_trade", "title": "The fuel bowser is waiting", "speaker": "Quartermaster",
         "text": "A supply unit can spare flight allocations if we release some engineering stores. It would get more aircraft into the air today, at the expense of tomorrow's repairs.",
         "choice": "Release the parts", "cost": {"parts": 2}, "gain": {"supplies": 4}, "detail": "Spend 2 parts; receive 4 supplies.", "result": "The quartermaster signs off the exchange. The flight allocations are ready."},
        {"kind": "intelligence", "title": "A fresh set of photographs", "speaker": "Intelligence officer",
         "text": "A reconnaissance unit has current photographs of our approaches. Sending transport to collect and interpret them would help this operation and the next.",
         "choice": "Send the transport", "cost": {"supplies": 2}, "gain": {}, "detail": "Spend 2 supplies; improve accuracy for this operation and the next.", "result": "Fresh photographs are pinned beside the route map.", "effect": "intel"},
        {"kind": "escort", "title": "A place in the escorted stream", "speaker": "Operations officer",
         "text": "Another group has room for us in its covered departure stream. Coordinating the slot uses stores, but it reduces exposure on this operation and the next.",
         "choice": "Coordinate the slot", "cost": {"supplies": 2}, "gain": {}, "detail": "Spend 2 supplies; reduce enemy exposure for this operation and the next.", "result": "The liaison officer confirms our place in the stream.", "effect": "disruption"},
    ]
    if usable and op < state["length"]:
        tired = max(usable, key=lambda p: p["fatigue"])
        if tired["fatigue"] >= 40:
            candidates.append({"kind": "leave", "title": f"{tired['captain']} asks for a day off the line", "speaker": tired["captain"], "plane": tired["id"],
                "text": "The crew is still willing to fly. The captain would rather they came back rested than spend another briefing pretending they are fine.",
                "choice": "Authorize leave", "cost": {}, "gain": {}, "detail": "Reduce this crew's fatigue by 45; unavailable for this operation.", "result": "Leave approved. Their chairs will be empty at this briefing, and occupied by a fresher crew at the next.", "fatigue": -45, "sit_out": True})
        green = min(usable, key=lambda p: p["skill"])
        if green["skill"] < .86:
            candidates.append({"kind": "training", "title": "An instructor has a spare seat", "speaker": "Training officer", "plane": green["id"],
                "text": f"{green['captain']}'s crew could spend this operation with a veteran instructor. They would miss today's assignment, but bring better habits to every sortie afterward.",
                "choice": "Assign the training", "cost": {"supplies": 2}, "gain": {}, "detail": "Spend 2 supplies; crew skill +8 percentage points; unavailable for this operation.", "result": "The crew leaves with the instructor's battered notebook. They will be back for the next operation.", "skill": .08, "sit_out": True})
        veteran = max(usable, key=lambda p: p["sorties"])
        if veteran["sorties"] >= 3:
            candidates.append({"kind": "mentoring", "title": "Let the veterans teach", "speaker": "Operations officer", "plane": veteran["id"],
                "text": f"We can take {veteran['captain']}'s crew off the roster today to pass on what they have learned. Every less experienced crew could benefit, but we would lose a dependable aircraft for this dispatch.",
                "choice": "Run the briefing clinic", "cost": {}, "gain": {}, "detail": "Veteran crew sits out this operation; other available crews below 85% skill gain 3 percentage points.", "result": "The briefing runs long. This time, the new crews do most of the listening.", "mentor": True, "sit_out": True})
    if state["losses"]:
        candidates.append({"kind": "letters", "title": "Letters on the adjutant's desk", "speaker": "Adjutant",
            "text": "The empty places are beginning to show. The adjutant asks for transport and time to let the remaining crews sit together away from the flight line.",
            "choice": "Give them the evening", "cost": {"supplies": 2}, "gain": {}, "detail": "Spend 2 supplies; all crews currently at the airfield recover 12 fatigue.", "result": "The mess stays open late. There are stories the official debrief never records.", "all_fatigue": -12})
    recent = state.get("decision_history", [])[-3:]
    fresh = [c for c in candidates if c["kind"] not in recent] or candidates
    result = dict(rng.choice(fresh))
    if op == state["length"]:
        for key in ("text", "detail"):
            result[key] = result[key].replace("this operation and the next", "this final operation")
    result["id"] = f"{op}:{result['kind']}"
    result["decline"] = "Keep our current arrangements"
    result["decline_detail"] = "No cost or change. Continue with the resources and crews you have."
    return result
