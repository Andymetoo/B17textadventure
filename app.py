from flask import Flask, render_template_string, request, session, redirect, url_for
from models import B17, CrewMember
from game_engine import Mission
import uuid

app = Flask(__name__)
app.secret_key = "B17_SECRET_KEY"  # Required for session management

# --- HTML TEMPLATE (Embedded for single-file simplicity) ---
HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>B-17: Text Command</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; background: #222; color: #ddd; padding: 20px; }
        .card { background: #333; padding: 15px; margin-bottom: 15px; border-radius: 8px; }
        .metric { font-size: 1.2em; font-weight: bold; color: #4CAF50; }
        .bar-container { background: #555; height: 20px; width: 100%; }
        .bar { height: 100%; background: #2196F3; }
        .log { background: #000; padding: 10px; font-family: monospace; border: 1px solid #444; }
        .warning { color: orange; } .danger { color: red; }
        select, button { width: 100%; padding: 10px; margin-top: 5px; font-size: 1rem;}
        button { background: #4CAF50; color: white; border: none; font-weight: bold; }
    </style>
</head>
<body>
    <h1>✈️ B-17 Command</h1>
    
    <div class="card">
        <p>Target: {{ mission.target_name }}</p>
        <p>Turn: <span class="metric">{{ mission.turn_number }}</span> | 
           Fuel: <span class="metric">{{ mission.fuel }}</span> | 
           Dist: <span class="metric">{{ mission.total_distance - mission.distance_covered }}</span></p>
    </div>

    {% if mission.is_complete %}
        <div class="card" style="border: 2px solid gold;">
            <h2>MISSION ENDED</h2>
            <a href="/reset"><button>Start New Mission</button></a>
        </div>
    {% else %}

    <div class="card">
        <h3>🛠️ Engines</h3>
        {% for hp in bomber.engines %}
            <div>Engine {{ loop.index }} ({{ hp }}%)</div>
            <div class="bar-container"><div class="bar" style="width: {{ hp }}%;"></div></div>
        {% endfor %}
        <p><small>Integrity: {{ status_text }}</small></p>
    </div>

    <form method="POST" action="/turn">
        <div class="card">
            <h3>👨‍✈️ Crew Orders</h3>
            {% for crew in bomber.crew_roster %}
                <div style="margin-bottom: 10px; border-bottom: 1px solid #444; padding-bottom: 5px;">
                    <strong>{{ crew.name }}</strong> <small>({{ crew.role }})</small>
                    <select name="{{ crew.name }}">
                        <option value="Passive">Passive</option>
                        <option value="Turret">Man Turret</option>
                        <option value="First Aid">First Aid</option>
                        <option value="Repair">Repair</option>
                        {% if crew.role == 'Pilot' %}
                            <option value="Evasive Action">Evasive Action</option>
                            <option value="Change Altitude">Change Altitude</option>
                        {% endif %}
                        {% if crew.role == 'Engineer' %}
                            <option value="Lean Mixture">Lean Mixture</option>
                        {% endif %}
                    </select>
                </div>
            {% endfor %}
            <button type="submit">EXECUTE NEXT 20 MILES ⏩</button>
        </div>
    </form>
    {% endif %}

    <div class="card">
        <h3>📻 Log</h3>
        <div class="log">
            {% for line in mission.latest_log %}
                <div class="{% if 'FLAK' in line or 'BANDITS' in line %}danger{% elif 'hit' in line %}warning{% endif %}">
                    > {{ line }}
                </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

# --- FLASK ROUTES ---

# Global storage for simplicity in this prototype. 
# In a real app, we'd pickle this into the session or a database.
GAME_STATE = {}

def get_mission():
    """Retrieve or create the mission for the current user."""
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
    
    if user_id not in GAME_STATE:
        # Initialize Game
        bomber = B17()
        skipper = CrewMember("Cpt. Reynolds", "Pilot", skill=10)
        miller = CrewMember("Sgt. Miller", "Gunner", skill=8)
        kowalski = CrewMember("Sgt. Kowalski", "Engineer", skill=7)
        bomber.add_crew_member(skipper, "Cockpit")
        bomber.add_crew_member(miller, "Waist")
        bomber.add_crew_member(kowalski, "Nose")
        GAME_STATE[user_id] = Mission(bomber)
    
    return GAME_STATE[user_id]

@app.route('/')
def index():
    mission = get_mission()
    bomber = mission.bomber
    status_text = " | ".join([f"{s.name}: {s.structure_hp}%" for s in bomber.sections.values()])
    return render_template_string(HTML_TEMPLATE, mission=mission, bomber=bomber, status_text=status_text)

@app.route('/turn', methods=['POST'])
def turn():
    mission = get_mission()
    # Convert form data to a dictionary
    crew_orders = request.form.to_dict()
    mission.resolve_turn(crew_orders)
    return redirect(url_for('index'))

@app.route('/reset')
def reset():
    session.pop('user_id', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
