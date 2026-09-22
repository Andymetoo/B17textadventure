# Fortress Command

A small, persistent B-17 airfield management prototype. Choose an operation,
commit a formation, and come back to the crews' reports. The captains handle
everything in the air, including turning back when continuing becomes unsafe.

This replaces the original single-bomber, crew-by-crew turn game.

## Run it

Python 3.10 or later is required (verified with Python 3.12).

```sh
python -m venv .venv
```

Activate the environment with `.venv\Scripts\activate` on Windows or
`source .venv/bin/activate` on macOS/Linux, then:

```sh
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

## Try a complete loop in five minutes

1. Review the two mission cards. Priority targets offer up to nine points;
   supporting operations offer fewer points plus additional supplies or parts.
2. Select three or four aircraft from the flight line. The formation estimate
   accounts for weather, experience, fatigue, and aircraft condition, but cannot
   promise that every aircraft will reach the target.
3. Dispatch the formation. Your first operation takes **two minutes**.
4. While it is away, consider repairing Paper Moon or resting a reserve crew.
5. Read the radio reports. Use **Prototype pacing → Fast-forward** to jump to
   the next scheduled report or completed ground job without real waiting.
6. Read the debrief, including the individual crew reports. Plan the next sortie
   using the aircraft, fatigue, and resources that actually remain.

Later flights take two or three hours, but fast-forward remains available by
default. It uses the same simulation and costs as normal elapsed time. Missions
and authorized ground work resolve while you are away; simply reopen the page.
No response deadline, midair choice, or notification needs your attention.

## The playable rules

- Six aircraft and their regular crews to start; requisition up to eight slots.
- Twelve operations per tour. Aim for 60 campaign points; 75 earns a distinction.
- One formation airborne at a time; its size is limited by readiness and supplies.
- Priority missions cost two supplies per aircraft; support costs one.
- Condition below 55 or fatigue at 85 or above prevents dispatch. Poorer condition
  and higher fatigue also affect outcomes before those grounding thresholds.
- Crew traits have specific effects: steady crews reduce incoming damage,
  navigators limit cloud penalties, and bombing specialists improve target effect.
- Repairs restore an aircraft to 100 condition in 45 minutes, consuming one part
  per 20 missing condition (rounded up). There is one maintenance bay.
- A recovery assignment consumes one supply and reduces fatigue by 55 after
  45 minutes. One crew can be on a recovery assignment at a time.
- Crews not dispatched recover 25 fatigue when an operation concludes.
- Before each new operation, the base receives four supplies and one part.
  Stores are capped at 30 supplies and 20 parts. Extra support allocations scale
  with target effect, rather than being guaranteed for merely launching.
- Additional/replacement aircraft and developing crews cost five supplies and
  three parts. Replacements occupy the missing aircraft's slot and retain the
  old aircraft's history in the debrief archive.
- Standing down costs an operation and earns no points, but provides reserve
  recovery and the next allocation. It is a recovery path, not an infinite farm.
- Time alone never generates new operations, free stores, automatic repairs, or
  unlimited crew recovery. There are no missed-login penalties.

## Architecture and saves

| File | Responsibility |
| --- | --- |
| `models.py` | Initial roster, JSON-safe campaign state, stable operation offers |
| `game_engine.py` | Validated player commands and deterministic scheduled events |
| `storage.py` | Transactional SQLite persistence and revision checks |
| `app.py` | Session identity, form validation, application factory, HTTP routes |
| `templates/airfield.html` | Responsive operations board and debrief archive |
| `static/airfield.*` | Presentation, countdowns, formation estimates, report polling |

The browser never resolves combat. Mission snapshots and seeds are saved at
dispatch; each phase uses a local deterministic random generator. Ground jobs
and mission phases resolve in timestamp order. Catching up once produces the
same campaign as checking repeatedly. Refreshing cannot reroll an encounter.

State is saved in `instance/campaigns.sqlite3`, and the generated signing key in
`instance/session.key`. Preserve **both** across restarts and deployments. The
browser's signed session cookie identifies its campaign. This prototype has no
accounts or cross-device sync: clearing cookies starts a different campaign.
Changing the signing key invalidates existing browser sessions.

SQLite transactions serialize commands; revision checks reject stale or duplicate
forms. CSRF tokens protect POST actions. GET requests can resolve already-due work
but cannot dispatch, spend resources, or reset a tour. Runtime databases, keys,
and Python caches are excluded from source control.

The development server runs on localhost without debug mode. For a hosted
installation, use a production WSGI server serving `app:app`, persistent storage,
HTTPS, and a configured stable secret. This is an anonymous prototype, not a
production account or notification service.

| Environment variable | Default / use |
| --- | --- |
| `B17_DATABASE` | `instance/campaigns.sqlite3` |
| `B17_SECRET_KEY` | Generated persistent local key; configure explicitly for hosting |
| `B17_SECURE_COOKIE` | Set to `1` when served over HTTPS |
| `B17_ALLOW_FAST_FORWARD` | `1`; set to `0` to disable the prototype timing control |
| `B17_HOST` | `127.0.0.1`; use `0.0.0.0` for deliberate network access |
| `PORT` | `5000` |

## Validation

```sh
python -m unittest discover -s tests -v
```

Tests cover the complete dispatch/debrief loop, autonomous returns, offline
equivalence, persistence across restart, concurrent and duplicate submissions,
resource costs, grounding and maintenance restrictions, recovery, replacement,
tour completion, CSRF, session isolation, and disabled fast-forward enforcement.

## Deliberate prototype limits

Aircraft retain their regular crews; individual crew transfers and injuries are
not modeled. Returning aircraft, including early turnbacks, are released to the
flight line at the operation's final return checkpoint. Communications use a
small collection of state-driven reports. There are no push notifications,
background auto-dispatches, base construction, equipment trees, or tactical crew
menus. Historical setting and mission durations are abstractions.

The next design work should follow human playtesting: tune the mission/resource
tradeoff, give familiar crews more distinct voices, and add situation-dependent
mission opportunities. Avoid adding management screens until the existing loop
is enjoyable across several operations.
