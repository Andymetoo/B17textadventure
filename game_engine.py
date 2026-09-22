"""Deterministic scheduled simulation, independent of HTTP and wall-clock access."""
import copy
import math
import random

from models import MAX_AIRCRAFT, briefing, new_aircraft


class RuleError(ValueError):
    pass


def aircraft(state, plane_id):
    for plane in state["aircraft"]:
        if plane["id"] == plane_id:
            return plane
    raise RuleError("That aircraft is not in this detachment.")


def airborne(state, plane_id):
    return bool(state["active"] and plane_id in state["active"]["plane_ids"])


def availability(state, plane):
    if plane["lost"]:
        return "Missing"
    if airborne(state, plane["id"]):
        return "On operation"
    if plane["job"]:
        return "In maintenance" if plane["job"]["kind"] == "repair" else "Crew recovering"
    if plane["condition"] < 55:
        return "Needs repair"
    if plane["fatigue"] >= 85:
        return "Crew exhausted"
    return "Available"


def effectiveness(plane, mission):
    visibility = {"Clear": 1, "Broken cloud": .88, "Overcast": .74}[mission["weather"]]
    if plane["trait"] == "navigator":
        visibility = min(1, visibility + .17)
    specialist = 1.12 if plane["trait"] == "precision" else 1
    return plane["skill"] * (.6 + .4 * plane["condition"] / 100) * (
        1 - plane["fatigue"] / 240) * visibility * specialist


def repair_cost(plane):
    return max(1, math.ceil((100 - plane["condition"]) / 20))


def message(state, at, speaker, text, tone="normal"):
    state["messages"].append({"at": at, "speaker": speaker, "text": text, "tone": tone})
    state["messages"] = state["messages"][-100:]


def require_open(state):
    if state["completed"]:
        raise RuleError("This tour is complete. Start a new tour to play again.")


def dispatch(state, mission_id, plane_ids, now):
    require_open(state)
    if state["active"]:
        raise RuleError("An operation is already in progress. Let the formation return first.")
    mission = next((m for m in briefing(state) if m["id"] == mission_id), None)
    if not mission:
        raise RuleError("Choose one of the current operations.")
    if not plane_ids or len(plane_ids) != len(set(plane_ids)):
        raise RuleError("Select at least one aircraft, with no duplicate selections.")
    planes = [aircraft(state, pid) for pid in plane_ids]
    if any(availability(state, p) != "Available" for p in planes):
        raise RuleError("One of those aircraft or crews is unavailable. Review the flight line.")
    cost = mission["cost"] * len(planes)
    if state["supplies"] < cost:
        raise RuleError("Insufficient supplies. Send fewer aircraft, take a supporting operation, or stand down.")
    duration = 120 if state["operation"] == 1 else mission["hours"] * 3600
    state["supplies"] -= cost
    state["active"] = {"operation": state["operation"], "mission": copy.deepcopy(mission),
        "plane_ids": list(plane_ids), "snapshots": copy.deepcopy(planes),
        "started": now, "returns": now + duration, "phase": 0,
        "due": [now + duration * .25, now + duration * .6, now + duration],
        "results": {}, "effect": 0, "cost": cost}
    message(state, now, "Operations", f"{len(planes)} aircraft dispatched to {mission['name']}. Captains have authority to turn back if their aircraft becomes unsafe.")


def start_job(state, plane_id, kind, now):
    require_open(state)
    plane = aircraft(state, plane_id)
    if plane["lost"] or plane["job"] or airborne(state, plane_id):
        raise RuleError("That aircraft is already committed or missing.")
    if kind == "repair":
        if plane["condition"] == 100:
            raise RuleError("This aircraft does not need repairs.")
        if any(p["job"] and p["job"]["kind"] == "repair" for p in state["aircraft"]):
            raise RuleError("The maintenance bay is occupied. Finish its current job first.")
        cost = repair_cost(plane)
        if state["parts"] < cost:
            raise RuleError("Insufficient spare parts for this repair.")
        state["parts"] -= cost
        duration = 45 * 60
        text = f"{plane['name']} is in the bay. {cost} spare parts committed; ready in 45 minutes."
    elif kind == "rest":
        if plane["fatigue"] == 0:
            raise RuleError("This crew is already rested.")
        if state["supplies"] < 1:
            raise RuleError("Crew recovery needs one supply allocation.")
        if any(p["job"] and p["job"]["kind"] == "rest" for p in state["aircraft"]):
            raise RuleError("The recovery transport is already assigned to another crew.")
        state["supplies"] -= 1
        duration = 45 * 60
        text = f"{plane['captain']}'s crew is off duty for 45 minutes. Fatigue will fall by 55."
    else:
        raise RuleError("Unknown ground assignment.")
    plane["job"] = {"kind": kind, "due": now + duration}
    message(state, now, "Chief mechanic" if kind == "repair" else "Operations", text)


def requisition(state, plane_id, now):
    require_open(state)
    if state["supplies"] < 5 or state["parts"] < 3:
        raise RuleError("A replacement aircraft and green crew cost 5 supplies and 3 parts.")
    if plane_id:
        old = aircraft(state, plane_id)
        if not old["lost"]:
            raise RuleError("Only a missing aircraft can be replaced.")
        index = state["aircraft"].index(old)
        plane = new_aircraft(index, old["replacement"] + 1)
        state["aircraft"][index] = plane
    else:
        if len(state["aircraft"]) >= MAX_AIRCRAFT:
            raise RuleError("The detachment has its full eight aircraft slots.")
        plane = new_aircraft(len(state["aircraft"]))
        state["aircraft"].append(plane)
    state["supplies"] -= 5
    state["parts"] -= 3
    message(state, now, "Operations", f"{plane['name']} has arrived with a green crew. A new aircraft gives us options, but they will need experience.")


def finish_operation(state, report, now, participants):
    # Reserve crews recover by operation, never by unattended wall-clock farming.
    for plane in state["aircraft"]:
        if plane["id"] not in participants and not plane["lost"]:
            plane["fatigue"] = max(0, plane["fatigue"] - 25)
    state["score"] += report["points"]
    state["debriefs"].append(report)
    state["operation"] += 1
    state["completed"] = state["operation"] > state["length"]
    if not state["completed"]:
        state["supplies"] = min(30, state["supplies"] + 4)
        state["parts"] = min(20, state["parts"] + 1)
    message(state, now, "Operations", report["summary"], "good" if report["points"] else "warning")


def stand_down(state, now):
    require_open(state)
    if state["active"]:
        raise RuleError("Cannot stand down while the formation is away.")
    report = {"operation": state["operation"], "target": "Stand down", "at": now,
              "points": 0, "effect": 0, "cost": 0, "bonus": "None", "results": [],
              "summary": "Operation stood down. No campaign progress; reserve crews recover 25 fatigue."}
    finish_operation(state, report, now, [])


def resolve_phase(state, at):
    flight = state["active"]
    mission = flight["mission"]
    phase = flight["phase"]
    for snapshot in flight["snapshots"]:
        pid = snapshot["id"]
        rng = random.Random(f"{state['seed']}:{flight['operation']}:{phase}:{pid}")
        if phase == 0:
            risk = mission["risk"] + snapshot["fatigue"] / 550 + (100 - snapshot["condition"]) / 350
            wear = rng.randint(2, 6)
            hit = rng.random() < risk
            damage = rng.randint(12, 32) if hit else 0
            if snapshot["trait"] == "steady":
                damage = round(damage * .7)
            condition = max(0, snapshot["condition"] - damage - wear)
            lost = hit and rng.random() < risk * .065
            aborted = not lost and (condition < 50 or (damage >= 20 and snapshot["fatigue"] > 55))
            notes = []
            if hit:
                notes.append(f"Enemy action caused {damage} condition damage.")
            if snapshot["fatigue"] > 55:
                notes.append("Crew fatigue increased exposure and reduced bombing effectiveness.")
            if snapshot["condition"] < 80:
                notes.append("Pre-existing wear increased exposure.")
            if aborted:
                notes.append("The captain turned back: continuing was unsafe.")
                message(state, at, snapshot["captain"], f"{snapshot['name']}: taking her home. We cannot safely continue.", "warning")
            elif lost:
                notes.append("Lost contact on the outbound leg. Aircraft and crew missing.")
                message(state, at, "Radio room", f"Contact lost with {snapshot['name']}. No confirmed return.", "warning")
            flight["results"][pid] = {"id": pid, "name": snapshot["name"], "captain": snapshot["captain"],
                "condition": condition, "lost": lost, "aborted": aborted, "contribution": 0,
                "fatigue": min(100, snapshot["fatigue"] + rng.randint(22, 32)), "notes": notes}
        elif phase == 1:
            result = flight["results"][pid]
            if result["lost"] or result["aborted"]:
                continue
            result["contribution"] = effectiveness(snapshot, mission) * rng.uniform(.85, 1.15)
            flight["effect"] += result["contribution"]
            if mission["weather"] != "Clear":
                result["notes"].append("Navigator limited the visibility penalty." if snapshot["trait"] == "navigator" else "Cloud reduced bombing effectiveness.")
            if snapshot["trait"] == "precision":
                result["notes"].append("Bombing specialist improved target effect.")
        else:
            result = flight["results"][pid]
            plane = aircraft(state, pid)
            if not result["lost"] and not result["aborted"]:
                if rng.random() < mission["risk"] * .6:
                    damage = rng.randint(5, 16)
                    if snapshot["trait"] == "steady":
                        damage = round(damage * .7)
                    result["condition"] = max(0, result["condition"] - damage)
                    result["notes"].append(f"Return-leg interception caused {damage} condition damage.")
                if result["condition"] < 35 and rng.random() < .2:
                    result["lost"] = True
                    result["notes"].append("Missing on the return leg; bombing contribution is retained.")
            plane["lost"] = result["lost"]
            plane["condition"] = result["condition"]
            plane["fatigue"] = result["fatigue"]
            if result["lost"]:
                state["losses"] += 1
            else:
                plane["sorties"] += 1
                plane["skill"] = min(1, plane["skill"] + .018)
            if not result["notes"]:
                result["notes"].append("Routine sortie. Normal wear and crew fatigue only.")
            result["status"] = "Missing" if result["lost"] else ("Returned early" if result["aborted"] else "Home")
    if phase == 0:
        continuing = sum(not r["lost"] and not r["aborted"] for r in flight["results"].values())
        message(state, at, "Radio room", f"Outbound report: {continuing} aircraft continuing toward the target. Crews are handling conditions on board.")
    elif phase == 1:
        message(state, at, "Radio room", "Target phase complete. Bombing reports are being compiled. The formation is heading home.")
    else:
        fraction = min(1, flight["effect"] / mission["required"])
        points = round(mission["reward"] * fraction)
        returned = sum(not r["lost"] for r in flight["results"].values())
        bonus = "None"
        if mission["bonus"] != "none":
            quantity = math.floor((6 if mission["bonus"] == "supplies" else 4) * fraction)
            state[mission["bonus"]] = min(30 if mission["bonus"] == "supplies" else 20, state[mission["bonus"]] + quantity)
            bonus = f"{quantity} {mission['bonus']}"
        report = {"operation": flight["operation"], "target": mission["name"], "at": at,
                  "points": points, "effect": round(fraction * 100), "cost": flight["cost"],
                  "bonus": bonus, "results": list(flight["results"].values()),
                  "summary": f"{returned} of {len(flight['plane_ids'])} aircraft home. Target effect {round(fraction * 100)}%; {points} campaign points. Extra allocation: {bonus.lower()}."}
        finish_operation(state, report, at, flight["plane_ids"])
        state["active"] = None
        return
    flight["phase"] += 1


def next_event(state):
    events = [(p["job"]["due"], "job", p["id"]) for p in state["aircraft"] if p["job"]]
    if state["active"]:
        flight = state["active"]
        events.append((flight["due"][flight["phase"]], "mission", ""))
    return min(events) if events else None


def advance(state, now):
    """Chronological catch-up: opening once or repeatedly yields identical outcomes."""
    while (event := next_event(state)) and event[0] <= now:
        at, kind, pid = event
        if kind == "mission":
            resolve_phase(state, at)
        else:
            plane = aircraft(state, pid)
            job = plane["job"]
            if job["kind"] == "repair":
                plane["condition"] = 100
                text = f"{plane['name']} is repaired and cleared for service."
            else:
                plane["fatigue"] = max(0, plane["fatigue"] - 55)
                text = f"{plane['captain']}'s crew has completed recovery."
            plane["job"] = None
            message(state, at, "Chief mechanic" if job["kind"] == "repair" else "Operations", text, "good")
