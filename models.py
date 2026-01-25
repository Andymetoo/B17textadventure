class CrewMember:
    def __init__(self, name, role, skill=5):
        self.name = name
        self.role = role
        self.skill = skill  # <--- This line was missing!
        self.hp = 100
        self.stress = 0
        # Assignments: 'Passive', 'Turret', 'Repairing', 'First Aid', 'Piloting'
        self.current_assignment = "Passive" 

    def __repr__(self):
        return f"<{self.name} ({self.role}) | HP:{self.hp} Stress:{self.stress} Skill:{self.skill}>"


class PlaneSection:
    def __init__(self, name):
        self.name = name
        self.structure_hp = 100
        self.is_on_fire = False
        self.is_depressurized = False
        # This list will hold actual CrewMember objects currently in this section
        self.stationed_crew = []

    def add_crew(self, crew_member):
        self.stationed_crew.append(crew_member)

    def remove_crew(self, crew_member):
        if crew_member in self.stationed_crew:
            self.stationed_crew.remove(crew_member)

class B17:
    def __init__(self):
        # The 4 Engines (0-100%)
        self.engines = [100, 100, 100, 100]
        
        # The Sections
        self.sections = {
            "Nose": PlaneSection("Nose"),
            "Cockpit": PlaneSection("Cockpit"),
            "Bomb Bay": PlaneSection("Bomb Bay"),
            "Waist": PlaneSection("Waist"),
            "Tail": PlaneSection("Tail")
        }
        
        # We also need a master list of crew to track them easily
        self.crew_roster = []

    def add_crew_member(self, crew_member, section_name):
        """Helper to place crew on the plane initially."""
        if section_name in self.sections:
            self.sections[section_name].add_crew(crew_member)
            self.crew_roster.append(crew_member)

    def calculate_defense_score(self):
        """
        Iterates through the plane to find crew assigned to 'Turret'.
        Defense = Sum of (Gunner Skill) + Formation Bonus (Flat 10 for now).
        """
        total_defense = 0
        formation_bonus = 10
        
        # Iterate through all sections
        for section_name, section_obj in self.sections.items():
            for crew in section_obj.stationed_crew:
                # Check if they are actually manning a gun
                if crew.current_assignment == "Turret":
                    # If they are stressed, their skill might be effective at 50% (future mechanic)
                    total_defense += crew.skill
                    print(f"  + {crew.name} is manning a turret! (+{crew.skill})")
        
        total_defense += formation_bonus
        return total_defense

# --- Quick Test to Verify Logic ---
if __name__ == "__main__":
    # 1. Instantiate the Plane
    my_bomber = B17()

    # 2. Create Crew
    miller = CrewMember("Miller", "Gunner", skill=8)
    skipper = CrewMember("The Skipper", "Pilot", skill=9)

    # 3. Assign them to initial sections (Physically where they are)
    my_bomber.add_crew_member(miller, "Waist")
    my_bomber.add_crew_member(skipper, "Cockpit")

    # 4. Set their "Action State" (What they are doing)
    miller.current_assignment = "Turret"
    skipper.current_assignment = "Piloting" # Pilot adds evasion, not defense

    # 5. Calculate Defense
    score = my_bomber.calculate_defense_score()
    print(f"Total Defense Score: {score}")
