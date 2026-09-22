"""Deterministic scheduled simulation, independent of HTTP and wall-clock access."""
import copy
import math
import random

from models import MAX_AIRCRAFT, briefing, new_aircraft
from content import HOME_LINES, MILESTONES, OUTBOUND_EVENTS, TARGET_EVENTS, TOUR_GOALS, TOUR_LENGTHS, ground_situation


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
        return "Written off" if plane.get("crew_fate") == "safe" else "Missing"
    if plane.get("away_until"):
        return "At another airfield"
    if plane.get("unavailable_until", 0) > state["operation"]:
        return plane.get("leave_reason") or "Crew on leave"
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
    specialist = (1.18 if mission.get("kind") == "industry" else 1.12) if plane["trait"] == "precision" and mission.get("kind") != "recon" else 1
    specialist *= 1.10 if mission.get("intel") else 1
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
    close_ground_decision(state, now)
    if mission_id == 'followup':
        state['opportunity'] = None
    state["supplies"] -= cost
    state["active"] = {"operation": state["operation"], "mission": copy.deepcopy(mission),
        "plane_ids": list(plane_ids), "snapshots": copy.deepcopy(planes),
        "started": now, "returns": now + duration, "phase": 0,
        "due": [now + duration * .25, now + duration * .6, now + duration],
        "results": {}, "effect": 0, "cost": cost, "rules_version": 2}
    message(state, now, "Operations", f"{len(planes)} aircraft dispatched to {mission['name']}. Captains have authority to turn back if their aircraft becomes unsafe.")


def start_job(state, plane_id, kind, now):
    require_open(state)
    plane = aircraft(state, plane_id)
    if plane["lost"] or plane["job"] or plane.get("away_until") or plane.get("unavailable_until", 0) > state["operation"] or airborne(state, plane_id):
        raise RuleError("That aircraft is already committed or missing.")
    if kind == "repair":
        if plane["condition"] == 100:
            raise RuleError("This aircraft does not need repairs.")
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
        state["supplies"] -= 1
        duration = 45 * 60
        text = f"{plane['captain']}'s crew is off duty for 45 minutes. Fatigue will fall by 55."
    else:
        raise RuleError("Unknown ground assignment.")
    starts = max([now] + [p["job"]["due"] for p in state["aircraft"] if p["job"] and p["job"]["kind"] == kind])
    plane["job"] = {"kind": kind, "starts": starts, "due": starts + duration}
    if starts > now:
        minutes = math.ceil((starts + duration - now) / 60)
        text = f"{plane['name']}: {('repairs' if kind == 'repair' else 'crew recovery')} booked behind the current work. Resources committed now; expected completion in {minutes} minutes."
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
        if old.get("crew_fate") == "safe":
            for field in ("captain", "skill", "trait", "fatigue", "sorties", "history", "milestones", "unavailable_until", "leave_reason"):
                plane[field] = copy.deepcopy(old.get(field, plane[field]))
            plane["history"].append({"operation": state["operation"], "text": "The surviving crew has been assigned a replacement aircraft."})
        state["aircraft"][index] = plane
    else:
        if len(state["aircraft"]) >= MAX_AIRCRAFT:
            raise RuleError("The detachment has its full eight aircraft slots.")
        plane = new_aircraft(len(state["aircraft"]))
        state["aircraft"].append(plane)
    state["supplies"] -= 5
    state["parts"] -= 3
    crew_text = "The surviving crew will fly her when cleared for duty." if plane_id and old.get("crew_fate") == "safe" else "A developing crew will need time to learn her ways."
    message(state, now, "Operations", f"{plane['name']} has arrived. {crew_text}")


def finish_operation(state, report, now, participants):
    # Reserve crews recover by operation, never by unattended wall-clock farming.
    for plane in state["aircraft"]:
        if plane["id"] not in participants and not plane["lost"] and not plane.get("away_until"):
            plane["fatigue"] = max(0, plane["fatigue"] - 25)
    state["score"] += report["points"]
    state["debriefs"].append(report)
    state["operation"] += 1
    state["completed"] = state["operation"] > state["length"]
    if not state["completed"]:
        state["supplies"] = min(30, state["supplies"] + 4)
        state["parts"] = min(20, state["parts"] + 1)
    message(state, now, "Operations", report["summary"], "good" if report["points"] else "warning")
    if state.get("opportunity") and state["opportunity"]["expires"] < state["operation"]:
        state["opportunity"] = None
    state["decision"] = ground_situation(state)


def stand_down(state, now):
    require_open(state)
    if state["active"]:
        raise RuleError("Cannot stand down while the formation is away.")
    close_ground_decision(state, now)
    report = {"operation": state["operation"], "target": "Stand down", "at": now,
              "points": 0, "effect": 0, "cost": 0, "bonus": "None", "results": [],
              "summary": "Operation stood down. No campaign progress; reserve crews recover 25 fatigue."}
    finish_operation(state, report, now, [])


def resolve_legacy_phase(state, at):
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
            plane["crew_fate"] = "missing" if result["lost"] else "safe"
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
    events.extend((p["away_until"], "diversion", p["id"]) for p in state["aircraft"] if p.get("away_until"))
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
        elif kind == "diversion":
            plane = aircraft(state, pid)
            plane["away_until"] = None
            text = f"{plane['name']} has returned from the diversion field. {plane['captain']}'s crew is back on our strength."
            remember(plane, state["operation"], text)
            message(state, at, "Radio room", text, "good")
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


def remember(plane, operation, text):
    plane.setdefault('history', []).append({'operation': operation, 'text': text})
    plane['history'] = plane['history'][-100:]


def set_tour_length(state, length):
    if length not in TOUR_LENGTHS:
        raise RuleError('Choose a 7-, 14-, 21-, or 28-operation tour.')
    if state['operation'] != 1 or state['active'] or state['debriefs']:
        raise RuleError('Tour length is set before the first dispatch. This tour is already underway.')
    state['length'], state['goal'] = length, TOUR_GOALS[length]


def decision_blocker(state):
    decision = state.get('decision')
    if not decision:
        return 'No decision is waiting.'
    if state['active'] or state['completed']:
        return 'Decisions at the command desk are made between operations.'
    for resource, cost in decision['cost'].items():
        if state[resource] < cost:
            return f"Requires {cost} {resource}; only {state[resource]} available."
    if decision.get('plane'):
        plane = aircraft(state, decision['plane'])
        if plane['lost'] or plane['job'] or plane.get('away_until') or plane.get('unavailable_until', 0) > state['operation']:
            return 'That crew is already committed. Keep the current arrangements or complete its ground assignment first.'
    return None


def close_ground_decision(state, now, accepted=False):
    decision = state.get('decision')
    if not decision:
        return
    text = decision['result'] if accepted else f"{decision['title']}: we kept our current arrangements."
    state['journal'].append({'operation': state['operation'], 'title': decision['title'], 'text': text})
    state['decision_history'].append(decision['kind'])
    state['decision_history'] = state['decision_history'][-10:]
    state['decision'] = None
    message(state, now, decision['speaker'], text, 'good' if accepted else 'normal')


def choose_ground(state, decision_id, choice, now):
    require_open(state)
    decision = state.get('decision')
    if not decision or decision['id'] != decision_id or choice not in ('accept', 'decline'):
        raise RuleError('That command-desk decision is no longer available.')
    if state['active']:
        raise RuleError('The formation has already departed; no midair decisions are needed.')
    if choice == 'decline':
        close_ground_decision(state, now)
        return
    if blocker := decision_blocker(state):
        raise RuleError(blocker)
    for resource, cost in decision['cost'].items():
        state[resource] -= cost
    for resource, gain in decision['gain'].items():
        state[resource] = min(30 if resource == 'supplies' else 20, state[resource] + gain)
    if effect := decision.get('effect'):
        state['effects'][effect] = max(state['effects'].get(effect, 0), min(state['length'], state['operation'] + 1))
    if decision.get('plane'):
        plane = aircraft(state, decision['plane'])
        plane['fatigue'] = max(0, plane['fatigue'] + decision.get('fatigue', 0))
        plane['skill'] = min(1, plane['skill'] + decision.get('skill', 0))
        if decision.get('sit_out'):
            plane['unavailable_until'] = state['operation'] + 1
            plane['leave_reason'] = 'Crew training' if decision.get('skill') or decision.get('mentor') else 'Crew on leave'
        if decision.get('mentor'):
            for trainee in state['aircraft']:
                if trainee['id'] != plane['id'] and not trainee['lost'] and not trainee.get('away_until') and trainee.get('unavailable_until', 0) <= state['operation'] and not trainee['job'] and trainee['skill'] < .85:
                    trainee['skill'] = min(.85, trainee['skill'] + .03)
        remember(plane, state['operation'], decision['result'])
    if decision.get('all_fatigue'):
        for plane in state['aircraft']:
            if not plane['lost'] and not plane.get('away_until'):
                plane['fatigue'] = max(0, plane['fatigue'] + decision['all_fatigue'])
    close_ground_decision(state, now, accepted=True)


def _outbound_result(snapshot, mission, rng):
    risk = mission['risk'] + snapshot['fatigue'] / 550 + (100 - snapshot['condition']) / 350
    event_roll = rng.random()
    if not mission.get('opening') and event_roll < .035 + (100 - snapshot['condition']) / 1500:
        event = OUTBOUND_EVENTS[3]
    elif not mission.get('opening') and event_roll < .085:
        event = OUTBOUND_EVENTS[4]
    elif mission['weather'] != 'Clear' and event_roll < .16:
        event = OUTBOUND_EVENTS[5]
    elif rng.random() < risk:
        event = rng.choice(OUTBOUND_EVENTS[1:3])
    else:
        event = OUTBOUND_EVENTS[0]
    damage = rng.randint(12, 30) if event['id'] in ('flak', 'fighters') else event.get('damage', 0)
    if snapshot['trait'] == 'steady' and event['id'] in ('flak', 'fighters'):
        damage = round(damage * .7)
    condition = max(0, snapshot['condition'] - damage - rng.randint(2, 5))
    lost = not mission.get('opening') and event['id'] in ('flak', 'fighters') and rng.random() < risk * .07
    medical = event.get('medical', False) or (not lost and damage >= 18 and rng.random() < .22)
    aborted = not lost and (event.get('abort', False) or condition < 48 or (medical and condition < 65))
    notes = [event['text'].format(name=snapshot['name'], captain=snapshot['captain'], damage=damage)]
    if snapshot['fatigue'] > 55:
        notes.append('An already tired crew had less margin for the unexpected; exposure was higher and target effectiveness lower.')
    if snapshot['condition'] < 80:
        notes.append('Pre-existing wear increased the chance of trouble on the route.')
    if mission.get('disruption'):
        notes.append('Recent airfield work or escort coordination reduced enemy exposure on this route.')
    if medical:
        notes.append('Crew members need treatment. This crew will sit out the next operation.')
    if aborted and not event.get('abort'):
        notes.append('The captain judged the aircraft unsafe to continue and turned back without waiting for permission.')
    if lost:
        notes.append('The last radio call ended abruptly. Aircraft and crew are listed as missing.')
    return {'id': snapshot['id'], 'name': snapshot['name'], 'captain': snapshot['captain'],
            'condition': condition, 'fatigue': min(100, snapshot['fatigue'] + rng.randint(20, 29) + event.get('fatigue', 0)),
            'lost': lost, 'crew_fate': 'missing' if lost else 'safe', 'medical': medical,
            'aborted': aborted, 'diverted': False, 'contribution': 0, 'notes': notes,
            'events': [event['id']], 'milestone': None}


def _target_result(snapshot, result, mission, rng):
    if result['lost'] or result['aborted']:
        return
    roll = rng.random()
    if mission.get('kind') == 'recon':
        if roll < .15:
            factor, event_id, text = .55, 'blurred_photos', 'The photographic run was disturbed by turbulence. Some frames are useful, but much of the coverage must be repeated.'
        elif roll > .83:
            factor, event_id, text = 1.18, 'clear_photos', 'The navigator held the line through a break in the weather. The cameras brought back unusually clear coverage of the defenses.'
        else:
            factor, event_id, text = 1, 'photos', 'The crew completed the photographic track. Intelligence has a usable set of route and defense pictures.'
    else:
        if roll < .045:
            event = TARGET_EVENTS[3]
        elif roll < (.24 if mission['weather'] == 'Overcast' else .10):
            event = TARGET_EVENTS[2]
        elif roll < .34:
            event = TARGET_EVENTS[4]
        elif roll > .90 and snapshot['skill'] >= .8:
            event = TARGET_EVENTS[5]
        elif roll > .78 and mission['weather'] != 'Clear':
            event = TARGET_EVENTS[1]
        else:
            event = TARGET_EVENTS[0]
        factor, event_id, text = event['factor'], event['id'], event['text']
    flying = dict(snapshot, condition=result['condition'])
    result['contribution'] = effectiveness(flying, mission) * rng.uniform(.9, 1.1) * factor
    result['events'].append(event_id)
    result['notes'].append(text.format(name=snapshot['name'], captain=snapshot['captain']))
    if mission['weather'] != 'Clear':
        result['notes'].append('The experienced navigator limited the cloud penalty.' if snapshot['trait'] == 'navigator' else 'Cloud reduced the accuracy of the run.')
    if mission.get('intel'):
        result['notes'].append('Recent reconnaissance gave the crew a better approach; target effectiveness improved.')


def _return_result(state, snapshot, result, mission, rng, at, operation):
    plane = aircraft(state, snapshot['id'])
    if not result['lost'] and not result['aborted']:
        if rng.random() < mission['risk'] * .55:
            damage = rng.randint(5, 15)
            if snapshot['trait'] == 'steady':
                damage = round(damage * .7)
            result['condition'] = max(0, result['condition'] - damage)
            result['notes'].append(f"An interception on the way home cost another {damage} condition. The crew kept the aircraft flying.")
            result['events'].append('return_interception')
        roll = rng.random()
        if not mission.get('opening') and result['condition'] < 55 and roll < .12:
            result['lost'], result['crew_fate'] = True, 'safe'
            result['notes'].append('The captain put her down in a field on the friendly side of the lines. All ten were recovered; the aircraft is a write-off. A replacement airframe can keep this crew together.')
            result['events'].append('forced_landing')
            result['medical'] = True
        elif not mission.get('opening') and roll > (.82 if mission['weather'] == 'Overcast' else .96):
            result['diverted'] = True
            plane['away_until'] = at + 6 * 3600
            result['notes'].append('Fuel and landing conditions sent the captain to another friendly airfield. Aircraft and crew are safe; expect them back in six hours. No action is required.')
            result['events'].append('diversion')
    plane['lost'], plane['crew_fate'] = result['lost'], result['crew_fate']
    plane['condition'], plane['fatigue'] = result['condition'], result['fatigue']
    if result['medical'] and result['crew_fate'] == 'safe':
        plane['unavailable_until'] = operation + 2
        plane['leave_reason'] = 'Medical leave'
    if result['lost']:
        state['losses'] += 1
    else:
        plane['sorties'] += 1
        plane['skill'] = min(1, plane['skill'] + .018)
        count = plane['sorties']
        if count in MILESTONES and count not in plane['milestones']:
            plane['milestones'].append(count)
            result['milestone'] = MILESTONES[count]
            result['notes'].append(MILESTONES[count])
            remember(plane, operation, MILESTONES[count])
        if not result['diverted']:
            result['notes'].append(rng.choice(HOME_LINES).format(name=plane['name'], captain=plane['captain']))
    result['status'] = ('Aircraft written off · crew recovered' if result['lost'] and result['crew_fate'] == 'safe' else
                        'Missing' if result['lost'] else 'Diverted · crew safe' if result['diverted'] else
                        'Returned early' if result['aborted'] else 'Home · crew needs treatment' if result['medical'] else 'Home')
    remember(plane, operation, f"{mission['name']}: {result['status']}.")


def _mission_consequences(state, flight, fraction):
    mission, op = flight['mission'], flight['operation']
    text = []
    bonus = 'None'
    if mission['bonus'] != 'none':
        resource = mission['bonus']
        quantity = math.floor(mission['bonus_max'] * fraction)
        cap = 30 if resource == 'supplies' else 20
        received = min(cap - state[resource], quantity)
        state[resource] += received
        bonus = f'{received} {resource}'
        if received < quantity:
            text.append(f'{quantity} {resource} were authorized; {received} fit in our stores.')
    if fraction >= .65:
        effect = mission.get('effect')
        remaining = min(2, state['length'] - op)
        if remaining == 0 and effect in ('intel', 'disruption', 'followup'):
            text.append('The objective was achieved. This tour ends before another sortie can use the follow-on advantage.')
            return bonus, text
        if effect in ('intel', 'disruption'):
            state['effects'][effect] = max(state['effects'].get(effect, 0), min(state['length'], op + 2))
            text.append(f'Reconnaissance improves accuracy through operation {min(state["length"], op + 2)}.' if effect == 'intel' else f'The enemy airfield is disrupted. Exposure is reduced through operation {min(state["length"], op + 2)}.')
        elif effect == 'followup':
            state['opportunity'] = {'opens': op + 1, 'expires': min(state['length'], op + 2), 'target': 'The stranded engine shipment',
                'description': f"Our strike on {mission['name']} held up an engine shipment. Intelligence has located its temporary assembly depot. We can follow it up through operation {min(state['length'], op + 2)}."}
            text.append(f'A shipment is stranded behind the damaged railway. A follow-up target is available through operation {min(state["length"], op + 2)}.')
    elif mission.get('effect') in ('intel', 'disruption', 'followup'):
        text.append('Target effect fell short of 65%; the planned follow-on advantage was not secured.')
    return bonus, text


def resolve_phase(state, at):
    flight = state['active']
    if flight.get('rules_version', 1) == 1:
        resolve_legacy_phase(state, at)
        return
    # Independent RNG streams prevent extra prose or a different selection order
    # from changing another aircraft's outcome.
    phase, mission, operation = flight['phase'], flight['mission'], flight['operation']
    for snapshot in flight['snapshots']:
        pid = snapshot['id']
        rng = random.Random(f"{state['seed']}:sortie-v2:{operation}:{phase}:{pid}")
        if phase == 0:
            result = _outbound_result(snapshot, mission, rng)
            flight['results'][pid] = result
            if result['aborted']:
                message(state, at, snapshot['captain'], f"{snapshot['name']}: we're bringing her back. The crew has the situation in hand, but continuing isn't safe.", 'warning')
            elif result['lost']:
                message(state, at, 'Radio room', f"No further word from {snapshot['name']}. We are keeping the frequency clear.", 'warning')
        elif phase == 1:
            result = flight['results'][pid]
            _target_result(snapshot, result, mission, rng)
            flight['effect'] += result['contribution']
        else:
            _return_result(state, snapshot, flight['results'][pid], mission, rng, at, operation)
    if phase == 0:
        count = sum(not r['lost'] and not r['aborted'] for r in flight['results'].values())
        message(state, at, 'Radio room', f"{count} aircraft continuing. The crews have crossed the first reporting point; the next word should come from the target area.")
    elif phase == 1:
        text = 'The photographic track is complete. Film is on its way home.' if mission['kind'] == 'recon' else 'Bombing runs are complete. Some reports are clearer than others; we will know more when the crews are on the ground.'
        message(state, at, 'Radio room', text)
    else:
        fraction = min(1, flight['effect'] / mission['required'])
        points = round(mission['reward'] * fraction)
        bonus, consequences = _mission_consequences(state, flight, fraction)
        results = list(flight['results'].values())
        home = sum(not r['lost'] and not r['diverted'] for r in results)
        diverted = sum(r['diverted'] for r in results)
        missing = sum(r['lost'] and r['crew_fate'] == 'missing' for r in results)
        written_off = sum(r['lost'] and r['crew_fate'] == 'safe' for r in results)
        arrivals = [f'{home} aircraft home']
        for count, label in [(diverted, 'diverted safely'), (missing, 'missing'), (written_off, 'written off with crews recovered')]:
            if count:
                arrivals.append(f'{count} {label}')
        summary = ', '.join(arrivals) + f'. Target effect {round(fraction * 100)}%; {points} campaign points.'
        if bonus != 'None':
            summary += f' Extra allocation: {bonus.lower()}.'
        report = {'operation': operation, 'target': mission['name'], 'at': at, 'points': points,
                  'effect': round(fraction * 100), 'cost': flight['cost'], 'bonus': bonus,
                  'results': results, 'summary': summary, 'consequences': consequences}
        finish_operation(state, report, at, flight['plane_ids'])
        state['active'] = None
        return
    flight['phase'] += 1
