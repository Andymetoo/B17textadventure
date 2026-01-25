class CrewMember:
    def __init__(self, name, role, skill=5):
        self.name = name
        self.role = role
        self.skill = skill
        self.hp = 100
        self.stress = 0
        # Assignments: 'Passive', 'Turret', 'Repairing', 'First Aid', 'Piloting'
        self.current_assignment = "Passive" 

    def __repr__(self):
        return f"<{self.name} ({self.role})>"

class PlaneSection:
    def __init__(self, name):
        self.name = name
        self.structure_hp = 100
        self.is_on_fire = False
        self.stationed_crew = []

    def add_crew(self, crew_member):
        if crew_member not in self.stationed_crew:
            self.stationed_crew.append(crew_member)

    def remove_crew(self, crew_member):
        if crew_member in self.stationed_crew:
            self.stationed_crew.remove(crew_member)

class B17:
    def __init__(self):
        # The 4 Engines (0-100%)
        self.engines = [100, 100, 100, 100]
        
        # The Full Plane Layout (8 Sections)
        self.sections = {
            "Nose": PlaneSection("Nose"),             # Bombardier / Navigator
            "Cockpit": PlaneSection("Cockpit"),       # Pilot / Co-Pilot
            "Top Turret": PlaneSection("Top Turret"), # Engineer
            "Bomb Bay": PlaneSection("Bomb Bay"),     # (Usually empty)
            "Radio": PlaneSection("Radio Room"),      # Radio Operator
            "Ball Turret": PlaneSection("Ball Turret"), # Ball Gunner
            "Waist": PlaneSection("Waist"),           # Waist Gunners
            "Tail": PlaneSection("Tail")              # Tail Gunner
        }
        
        self.crew_roster = []

    def add_crew_member(self, crew_member, section_name):
        """Helper to place crew on the plane initially."""
        if section_name in self.sections:
            self.sections[section_name].add_crew(crew_member)
            self.crew_roster.append(crew_member)

    def get_crew_section(self, crew_member):
        """Finds where a crew member is currently located."""
        for section in self.sections.values():
            if crew_member in section.stationed_crew:
                return section
        return None

    def calculate_defense_score(self):
        total_defense = 0
        formation_bonus = 15 # Increased bonus for full crew
        
        for section in self.sections.values():
            for crew in section.stationed_crew:
                if crew.current_assignment == "Turret":
                    total_defense += crew.skill
        
        return total_defense + formation_bonus