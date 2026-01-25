from flask import Flask, render_template_string, request, session, redirect, url_for
from models import B17, CrewMember
from game_engine import Mission
import uuid

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
            /* Palette - Dark Military/Retro Cockpit */
            --background: #1c1a17;
            --foreground: #e6e1cd;
            --primary: #ffae00;      /* Amber Glow */
            --primary-dim: #b37a00;
            --secondary: #3d4a2e;    /* Olive Drab */
            --secondary-fg: #e6e1cd;
            --destructive: #a32929;  /* Warning Red */
            --muted: #2a2825;
            --border: #44403c;
            
            /* Fonts */
            --font-display: 'Oswald', sans-serif;
            --font-body: 'Special Elite', monospace;
            --font-mono: 'Share Tech Mono', monospace;
        }

        /* --- GLOBAL STYLES & CRT EFFECT --- */
        body {
            background-color: var(--background);
            color: var(--foreground);
            font-family: var(--font-body);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
            position: relative;
            overflow-x: hidden;
        }

        /* Scanline Overlay */
        body::after {
            content: " ";
            display: block;
            position: fixed;
            top: 0; left: 0; bottom: 0; right: 0;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.1) 50%), 
                        linear-gradient(90deg, rgba(255, 0, 0, 0.03), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.03));
            background-size: 100% 2px, 3px 100%;
            pointer-events: none;
            z-index: 999;
            opacity: 0.6;
        }

        h1, h2, h3 {
            font-family: var(--font-display);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 0;
        }

        /* --- COMPONENTS --- */
        .container {
            max-width: 1000px;
            margin: 0 auto;
            position: relative;
            z-index: 10;
        }

        /* Card Component */
        .card {
            background: rgba(30, 30, 30, 0.6);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            backdrop-filter: blur(4px);
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }

        /* Header / Stats Bar */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            text-align: center;
            margin-bottom: 20px;
        }
        .stat-box {
            background: var(--muted);
            border: 1px solid var(--border);
            padding: 10px;
            border-radius: 4px;
        }
        .stat-label {
            font-family: var(--font-display);
            font-size: 0.8rem;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        .stat-value {
            font-family: var(--font-mono);
            font-size: 1.5rem;
            color: var(--primary);
            text-shadow: 0 0 10px rgba(255, 174, 0, 0.5);
        }

        /* Gauges (Progress Bars) */
        .gauge-container {
            margin-bottom: 15px;
            background: #111;
            padding: 10px;
            border: 1px solid #333;
            border-radius: 4px;
        }
        .gauge-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            font-family: var(--font-mono);
            font-size: 0.9rem;
        }
        .progress-track {
            height: 12px;
            background: #222;
            border: 1px solid #444;
            border-radius: 2px;
            overflow: hidden;
            position: relative;
        }
        .progress-fill {
            height: 100%;
            background: var(--primary);
            box-shadow: 0 0 10px var(--primary);
            transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .progress-fill.danger {
            background: var(--destructive);
            box-shadow: 0 0 10px var(--destructive);
            animation: pulse 1s infinite;
        }

        /* Crew Controls */
        .crew-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 15px;
        }
        .crew-card {
            background: var(--secondary);
            border: 1px solid #4a5a3a;
            padding: 10px;
            border-radius: 4px;
        }
        .crew-name {
            font-family: var(--font-display);
            color: #fff;
            border-bottom: 1px solid rgba(255,255,255,0.2);
            padding-bottom: 5px;
            margin-bottom: 10px;
        }
        select {
            width: 100%;
            background: #1a1a1a;
            color: var(--foreground);
            border: 1px solid var(--primary-dim);
            padding: 8px;
            font-family: var(--font-mono);
            font-size: 0.9rem;
            outline: none;
        }

        /* Action Button */
        .btn-main {
            width: 100%;
            background: var(--primary-dim);
            color: #1a1a1a;
            font-family: var(--font-display);
            font-size: 1.5rem;
            padding: 15px;
            border: none;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 2px;
            clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
            transition: all 0.2s;
        }
        .btn-main:hover {
            background: var(--primary);
            box-shadow: 0 0 20px var(--primary);
            transform: translateY(-2px);
        }

        /* Logs - Typewriter Style */
        .log-container {
            background: rgba(0,0,0,0.8);
            border: 1px solid var(--border);
            height: 300px;
            overflow-y: auto;
            padding: 15px;
            font-family: var(--font-mono);
            font-size: 0.9rem;
            border-left: 4px solid var(--primary);
        }
        .log-entry {
            margin-bottom: 8px;
            border-bottom: 1px solid #333;
            padding-bottom: 4px;
        }
        .log-entry.danger { color: var(--destructive); font-weight: bold; }
        .log-entry.warning { color: #facc15; }
        .log-entry.success { color: #4ade80; }
        .cursor { display: inline-block; width: 8px; height: 14px; background: var(--primary); animation: blink 1s infinite; }

        /* Animations */
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }
        @keyframes blink { 0% { opacity: 0; } 50% { opacity: 1; } 100% { opacity: 0; } }
        
        /* Utility */
        .text-right { text-align: right; }
        .fire-badge {
            background: var(--destructive);
            color: white;
            padding: 2px 6px;
            font-size: 0.7rem;
            border-radius: 4px;
            animation: pulse 0.5s infinite;
        }
    </style>
</head>
<body>

    <div class="container">
        
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px; border-bottom: 2px solid var(--border); padding-bottom: 10px;">
            <div>
                <h1 style="color: var(--foreground); margin-bottom:0;">FORTRESS COMMAND</h1>
                <small style="font-family: var(--font-mono); color: var(--primary);">MISSION: {{ mission.target_name }}</small>
            </div>
            <div style="text-align:right;">
                <div style="font-family: var(--font-display); font-size: 1.2rem;">TOP SECRET</div>
                <small>USAELF // 1943</small>
            </div>
        </div>

        {% if mission.is_complete %}
            <div class="card" style="border: 2px solid var(--primary); text-align: center;">
                <h2 style="font-size: 3rem; color: var(--primary);">MISSION ENDED</h2>
                <p style="font-family: var(--font-mono);">FINAL STATUS: {{ "SUCCESS" if mission.mission_success else "FAILURE" }}</p>
                <a href="/reset"><button class="btn-main">RETURN TO BASE (RESET)</button></a>
            </div>
        {% else %}

        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-label">Distance</div>
                <div class="stat-value">{{ mission.total_distance - mission.distance_covered }} <span style="font-size:0.8rem">mi</span></div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Fuel</div>
                <div class="stat-value">{{ mission.fuel }} <span style="font-size:0.8rem">lbs</span></div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Turn</div>
                <div class="stat-value">{{ mission.turn_number }}</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            
            <div>
                <div class="card">
                    <h3>🛠️ ENGINEERING</h3>
                    
                    {% for hp in bomber.engines %}
                    <div class="gauge-container">
                        <div class="gauge-header">
                            <span>ENGINE {{ loop.index }}</span>
                            <span style="color: {{ 'var(--destructive)' if hp < 50 else 'var(--primary)' }}">{{ hp }}%</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-fill {{ 'danger' if hp < 50 else '' }}" style="width: {{ hp }}%;"></div>
                        </div>
                    </div>
                    {% endfor %}

                    <hr style="border-color: var(--border); margin: 15px 0;">

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        {% for section in bomber.sections.values() %}
                        <div style="background: #222; padding: 8px; border: 1px solid {{ 'var(--destructive)' if section.is_on_fire else '#444' }};">
                            <div style="display:flex; justify-content:space-between;">
                                <strong style="font-size:0.8rem;">{{ section.name }}</strong>
                                {% if section.is_on_fire %}<span class="fire-badge">FIRE</span>{% endif %}
                            </div>
                            <div class="progress-track" style="height: 4px; margin-top: 5px;">
                                <div class="progress-fill {{ 'danger' if section.structure_hp < 40 else '' }}" style="width: {{ section.structure_hp }}%;"></div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>

            <div>
                <div class="card" style="padding:0; overflow:hidden;">
                    <div style="background: #000; padding: 5px 15px; border-bottom: 1px solid #333; font-family: var(--font-mono); font-size: 0.8rem; color: #666;">
                        RADIO TRANSCRIPTS
                    </div>
                    <div class="log-container" id="logBox">
                        {% for line in mission.latest_log %}
                            <div class="log-entry 
                                {% if 'FLAK' in line or 'BANDITS' in line or 'FIRE' in line %}danger
                                {% elif 'hit' in line or 'damage' in line %}warning
                                {% elif 'patched' in line or 'extinguished' in line %}success{% endif %}">
                                <span style="opacity:0.5; margin-right:5px;">></span> {{ line }}
                            </div>
                        {% endfor %}
                        <div class="cursor"></div>
                    </div>
                </div>

                <form method="POST" action="/turn">
                    <div class="card">
                        <h3>👨‍✈️ SQUADRON ORDERS</h3>
                        <div class="crew-grid">
                            {% for crew in bomber.crew_roster %}
                                <div class="crew-card">
                                    <div class="crew-name">{{ crew.name }}</div>
                                    <div style="font-size:0.7rem; color: #aaa; margin-bottom: 5px;">
                                        {{ crew.role }} | HP: {{ crew.hp }}
                                    </div>
                                    <select name="{{ crew.name }}">
                                        <option value="Passive">HOLD POSITION</option>
                                        <option value="Turret" style="color:var(--primary);">⌖ MAN TURRET</option>
                                        <option value="Repair" style="color:#4ade80;">🔧 REPAIR</option>
                                        <option value="First Aid" style="color:#f87171;">✚ FIRST AID</option>
                                        {% if crew.role == 'Pilot' %}
                                            <option value="Evasive Action">⚡ EVASIVE ACTION</option>
                                            <option value="Change Altitude">✈ CHANGE ALTITUDE</option>
                                        {% endif %}
                                        {% if crew.role == 'Engineer' %}
                                            <option value="Lean Mixture">💧 LEAN MIXTURE</option>
                                        {% endif %}
                                    </select>
                                </div>
                            {% endfor %}
                        </div>
                        <br>
                        <button type="submit" class="btn-main">EXECUTE MANEUVER</button>
                    </div>
                </form>
            </div>
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
    """Retrieve or create the mission for the current user."""
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
    
    if user_id not in GAME_STATE:
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
    return render_template_string(HTML_TEMPLATE, mission=mission, bomber=mission.bomber)

@app.route('/turn', methods=['POST'])
def turn():
    mission = get_mission()
    crew_orders = request.form.to_dict()
    mission.resolve_turn(crew_orders)
    return redirect(url_for('index'))

@app.route('/reset')
def reset():
    session.pop('user_id', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)