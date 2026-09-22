"""A deliberately simple once-daily commander, for regression/balance probes.

This is not an optimal policy and does not establish whether the game is fun.
Run from any directory: python tools/simulate_tours.py --runs 100
"""
import argparse
from collections import Counter
from pathlib import Path
from statistics import mean
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from game_engine import (advance, availability, choose_ground, decision_blocker,
                         dispatch, effectiveness, repair_cost, requisition,
                         stand_down, start_job)
from models import briefing, new_campaign


def run_tour(seed, length):
    state = new_campaign(seed, length=length)
    events, situations = Counter(), Counter()
    now, stood_down = 1000, 0
    while not state['completed']:
        advance(state, now)
        decision = state['decision']
        if decision:
            situations[decision['kind']] += 1
            accept = ((decision['kind'] == 'parts_trade' and state['parts'] < 3) or
                      (decision['kind'] == 'fuel_trade' and state['supplies'] < 6) or
                      (decision['kind'] in ('intelligence', 'escort') and state['supplies'] > 14))
            choose_ground(state, decision['id'], 'accept' if accept and not decision_blocker(state) else 'decline', now)
        missing = next((p for p in state['aircraft'] if p['lost']), None)
        if missing and sum(not p['lost'] for p in state['aircraft']) < 5 and state['supplies'] >= 11 and state['parts'] >= 5:
            requisition(state, missing['id'], now)
        offers = briefing(state)
        mission = next((m for m in offers if m['id'] == 'followup'), offers[0]) if state['supplies'] >= 8 else offers[1]
        ready = sorted((p for p in state['aircraft'] if availability(state, p) == 'Available'),
                       key=lambda p: effectiveness(p, mission), reverse=True)
        count = min(len(ready), state['supplies'] // mission['cost'], 4 if mission['cost'] == 2 else 3)
        if count:
            dispatch(state, mission['id'], [p['id'] for p in ready[:count]], now)
        else:
            stand_down(state, now)
            stood_down += 1
        # Queue only reserve work during this visit. Never fast-forward a job to
        # gain aircraft for the same day's dispatch: this models one visit/day.
        if not state['completed']:
            for plane in sorted(state['aircraft'], key=lambda p: p['condition']):
                if availability(state, plane) not in ('Available', 'Needs repair', 'Crew exhausted'):
                    continue
                if plane['condition'] < 80 and state['parts'] >= repair_cost(plane):
                    start_job(state, plane['id'], 'repair', now)
                elif plane['fatigue'] >= 65 and state['supplies'] > 2:
                    start_job(state, plane['id'], 'rest', now)
        now += 24 * 3600
        advance(state, now)
        for result in state['debriefs'][-1]['results']:
            events.update(result.get('events', []))
        assert state['supplies'] >= 0 and state['parts'] >= 0
        assert all(0 <= p['condition'] <= 100 and 0 <= p['fatigue'] <= 100 for p in state['aircraft'])
    return state, stood_down, events, situations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=100)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    all_events, all_situations = Counter(), Counter()
    for length in (7, 14, 21, 28):
        scores, losses, rests, won = [], [], [], 0
        for seed in range(args.runs):
            state, standdowns, events, situations = run_tour(seed, length)
            scores.append(state['score'])
            losses.append(state['losses'])
            rests.append(standdowns)
            won += state['score'] >= state['goal']
            all_events.update(events)
            all_situations.update(situations)
        print(f"{length:2d} operations | mean score {mean(scores):5.1f}/{state['goal']} | goal met {won}/{args.runs} | mean losses {mean(losses):.2f} | stand-downs {mean(rests):.2f}")
    print('Outcome variants reached:', ', '.join(sorted(all_events)))
    print('Ground situations reached:', ', '.join(sorted(all_situations)))


if __name__ == '__main__':
    main()
