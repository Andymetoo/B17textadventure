from flask import Flask, render_template_string, request, session, redirect, url_for
from models import B17, CrewMember
from game_engine import Mission
import uuid
import random # Needed for random skill generation

app = Flask(__name__)
app.secret_key = "B17_SECRET_KEY"

# --- THE RETRO MILITARY THEME (Embedded CSS/HTML) ---
HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>FORTRESS COMMAND // 1943</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;700&family=Share+Tech+Mono&family=Special+Elite&display=swap" rel="stylesheet">
    
    <style>
        :root {
            --background: #1c1a17;
            --foreground: #e6e1cd;
            --primary: #ffae00;
            --primary-dim: #b37a00;
            --secondary: #3d4a2e;
            --destructive: #a32929;
            --border: #44403c;
            --font-display: 'Oswald', sans-serif;
            --font-body: 'Special Elite', monospace;
            --font-mono: 'Share Tech Mono', monospace;
        }

        body {
            background-color: var(--background);
            color: var(--foreground);
            font-family: var(--font-body);
            margin: 0; padding: 10px;
            overflow-x: hidden;
        }
        
        /* CRT Effect */
        body::after {
            content: " "; display: block; position: fixed;
            top: 0; left: 0; bottom: 0; right: 0;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.1) 50%);
            background-size: 100% 2px;
            pointer-events: none; z-index: 999; opacity: 0.4;
        }

        .container { max-width: 1200px; margin: 0 auto; position: relative; z-index: 10; }

        .card {
            background: rgba(30, 30, 30, 0.6);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 15px; margin-bottom: 20px;
        }

        .stats-grid {
            display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px; text-align: center;
        }
        .stat-value { font-family: var(--font-mono); font-size: 1.5rem; color: var(--primary); }

        .crew-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 15px;
        }
        
        .crew-card {
            background: var(--secondary);
            border: 1px solid #556b2f;
            padding: 10px;
        }

        .section-status {
            display: flex; justify-content: space-between;
            background: #222; padding: 8px; margin-bottom: 5px;
            border-left: 4px solid #555;
            font-family: var(--font-mono);
        }
        .section-status.fire { border-left-color: var(--destructive); background: #3d1a1a; animation: blink 1s infinite; }

        select {
            width: 100%; background: #111; color: white;
            border: 1px solid #555; padding: 8px; margin-top: 5px;
            font-family: var(--font-mono);
        }

        .btn-main {
            width: 100%; background: var(--primary); color: black;
            font-family: var(--font-display); font-size: 1.5rem;
            padding: 15px; border: none; cursor: pointer;
            font-weight: bold; text-transform: uppercase;
        }
        .btn-main:hover { background: #ffcc00; }

        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        
        .log-box {
            height: 300px; overflow-y: auto; background: black;
            border: 1px solid #444; padding: 10px;
            font-family: var(--font-mono); font-size: 0.9rem;
        }
        .log-entry { margin-bottom: 4px; border-bottom: 1px solid #222; padding-bottom: 2px; }
        .danger { color: #ff5555; }
        .warning { color: #ffaa00; }
        .success { color: #55ff55; }
    </style>
</head>
<body>
    <div class="container">
        
        <div style="display:flex; justify-content:space-between; align-items:flex-end; border-bottom: 2px solid var(--border); margin-bottom: 20px;">
            <h1 style="margin:0; font-size: 2rem; color: var(--primary);">FORTRESS COMMAND</h1>
            <span style="font-family: var(--font-mono);">MISSION #115</span>
        </div>

        {% if mission.is_complete %}
            <div class="card" style="text-align: center; border: 2px solid var(--primary);">
                <h2 style="color: var(--primary); font-size: 3rem;">MISSION ENDED</h2>
                <p style="font-size: 1.5rem;">STATUS: {{ "SUCCESS" if mission.mission_success else "FAILURE" }}</p>
                <div style="margin: 20px 0;">
                    {% if mission.mission_success %}
                        <p style="color: #4ade80;">TARGET DESTROYED. EXCELLENT WORK COMMANDER.</p>
                    {% else %}
                        <p style="color: #ef4444;">MISSION FAILED. REVIEW LOGS.</p>
                    {% endif %}
                </div>
                <a href="/reset"><button class="btn-main">NEW MISSION</button></a>
            </div>
        {% else %}

        <div class="stats-grid">
            <div class="card" style="margin:0;">
                <div style="font-size:0.8rem; color:#888;">DISTANCE</div>
                <div class="stat-value">{{ mission.total_distance - mission.distance_covered }}</div>
            </div>
            <div class="card" style="margin:0;">
                <div style="font-size:0.8rem; color:#888;">FUEL</div>
                <div class="stat-value">{{ mission.fuel }}</div>
            </div>
            <div class="card" style="margin:0;">
                <div style="font-size:0.8rem; color:#888;">TURN</div>
                <div class="stat-value">{{ mission.turn_number }}</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 20px;">
            
            <div>
                <div class="card">
                    <h3>✈ SECTIONS</h3>
                    {% for section_name, section in bomber.sections.items() %}
                        <div class="section-status {{ 'fire' if section.is_on_fire else '' }}">
                            <div>
                                <strong>{{ section.name }}</strong>
                                {% if section.is_on_fire %}<span style="color:red; font-weight:bold;"> FIRE!</span>{% endif %}
                            </div>
                            <div style="color: {{ 'red' if section.structure_hp < 50 else 'white' }}">
                                {{ section.structure_hp }}%
                            </div>
                        </div>
                    {% endfor %}
                    <div style="margin-top: 10px; font-size: 0.8rem; color: #888;">
                        * Move crew to a section to REPAIR it.
                    </div>
                </div>

                <div class="card">
                    <h3>⚙ ENGINES</h3>
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:5px; font-family:var(--font-mono);">
                    {% for hp in bomber.engines %}
                        <div style="background:#222; padding:5px; text-align:center;">
                            E{{ loop.index }}: {{ hp }}%
                        </div>
                    {% endfor %}
                    </div>
                </div>
            </div>

            <form method="POST" action="/turn">
                <div class="card">
                    <h3>👨‍✈️ CREW ROSTER</h3>
                    <div class="crew-grid">
                        {% for crew in bomber.crew_roster %}
                            <div class="crew-card">
                                <div style="display:flex; justify-content:space-between;">
                                    <strong>{{ crew.name }}</strong>
                                    <small style="color:{{ 'red' if crew.hp < 50 else '#888' }}">HP: {{ crew.hp }}</small>
                                </div>
                                <div style="font-size: 0.75rem; color: var(--primary); margin-bottom: 5px;">
                                    {{ crew.role }} | <span style="color:white;">Loc: {{ bomber.get_crew_section(crew).name }}</span>
                                </div>
                                
                                <select name="{{ crew.name }}">
                                    <option value="Passive">Hold Position</option>
                                    
                                    <optgroup label="Actions">
                                        <option value="Turret">⌖ Man Guns</option>
                                        <option value="Repair">🔧 Repair / Firefight</option>
                                        <option value="First Aid">✚ First Aid</option>
                                    </optgroup>
                                    
                                    {% if crew.role == 'Pilot' or crew.role == 'Co-Pilot' %}
                                        <optgroup label="Pilot Controls">
                                            <option value="Evasive Action">⚡ Evasive Action</option>
                                        </optgroup>
                                    {% endif %}
                                    {% if crew.role == 'Engineer' %}
                                        <optgroup label="Engineer Controls">
                                            <option value="Lean Mixture">💧 Lean Mixture</option>
                                        </optgroup>
                                    {% endif %}

                                    <optgroup label="Move To...">
                                        {% for sec_name in bomber.sections.keys() %}
                                            {% if sec_name != bomber.get_crew_section(crew).name %}
                                                <option value="Move to {{ sec_name }}">➡ {{ sec_name }}</option>
                                            {% endif %}
                                        {% endfor %}
                                    </optgroup>
                                </select>
                            </div>
                        {% endfor %}
                    </div>
                </div>
                
                <div class="card">
                    <h3>📻 MISSION LOG</h3>
                    <div class="log-box" id="logBox">
                        {% for line in mission.latest_log %}
                            <div class="log-entry 
                                {% if 'FIRE' in line or 'CRITICAL' in line or 'FLAK' in line %}danger
                                {% elif 'hit' in line %}warning
                                {% elif 'repaired' in line or 'EXTINGUISHED' in line %}success{% endif %}">
                                > {{ line }}
                            </div>
                        {% endfor %}
                    </div>
                </div>

                <button type="submit" class="btn-main">EXECUTE TURN</button>
            </form>
        </div>
        {% endif %}
    </div>
    <script>
        var logBox = document.getElementById("logBox");
        if(logBox) logBox.scrollTop = logBox.scrollHeight;
    </script>
</body>
</html>
"""

# --- FLASK ROUTES ---
GAME_STATE = {}

def get_mission():
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
    
    if user_id not in GAME_STATE:
        bomber = B17()
        
        # --- THE FULL 10-MAN ROSTER ---
        # (Name, Role, Initial Location)
        roster_data = [
            ("Lt. Morgan", "Bombardier", "Nose"),
            ("Lt. Kowalski", "Navigator", "Nose"),
            ("Cpt. Reynolds", "Pilot", "Cockpit"),
            ("Lt. Halloway", "Co-Pilot", "Cockpit"),
            ("Sgt. Miller", "Engineer", "Top Turret"),
            ("Sgt. Valenti", "Radio Op", "Radio"),
            ("Sgt. Jones", "Ball Turret", "Ball Turret"),
            ("Sgt. O'Neal", "Waist Gunner", "Waist"),
            ("Sgt. Schmidt", "Waist Gunner", "Waist"),
            ("Sgt. Rossi", "Tail Gunner", "Tail")
        ]
        
        for name, role, section in roster_data:
            c = CrewMember(name, role, skill=random.randint(6, 10))
            bomber.add_crew_member(c, section)
            
        GAME_STATE[user_id] = Mission(bomber)
    
    return GAME_STATE[user_id]

@app.route('/')
def index():
    mission = get_mission()
    return render_template_string(HTML_TEMPLATE, mission=mission, bomber=mission.bomber)

@app.route('/turn', methods=['GET', 'POST'])
def turn():
    # Safety Net: If the browser tries to 'visit' /turn directly (GET),
    # just redirect them back to the dashboard.
    if request.method == 'GET':
        return redirect(url_for('index'))

    # Standard Logic (POST)
    mission = get_mission()
    mission.resolve_turn(request.form.to_dict())
    return redirect(url_for('index'))

@app.route('/reset')
def reset():
    session.pop('user_id', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)