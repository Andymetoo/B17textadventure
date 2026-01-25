import random

class Mission:
    def __init__(self, bomber_obj):
        self.bomber = bomber_obj
        self.target_name = "Ball Bearing Factory at Schweinfurt"
        self.total_distance = 400
        self.distance_covered = 0
        self.fuel = 1000 
        self.turn_number = 1
        self.is_complete = False
        self.mission_success = False
        self.latest_log = ["Mission Start. Good luck, Commander."]

    def resolve_turn(self, crew_orders):
        turn_log = []
        turn_log.append(f"--- Turn {self.turn_number} (Mile {self.distance_covered}) ---")

        active_gunners = 0
        evasive_maneuvers = False
        lean_mixture = False

        # --- CREW ACTIONS ---
        for member in self.bomber.crew_roster:
            action = crew_orders.get(member.name, "Passive")
            member.current_assignment = action
            
            # Find Section
            current_section = None
            for sec in self.bomber.sections.values():
                if member in sec.stationed_crew:
                    current_section = sec
                    break
            
            if action == "Repair" and current_section:
                if current_section.is_on_fire:
                    current_section.is_on_fire = False
                    turn_log.append(f"🧯 {member.name} EXTINGUISHED fire in {current_section.name}!")
                elif current_section.structure_hp < 100:
                    repair_val = random.randint(5, 15) + (member.skill // 2)
                    current_section.structure_hp = min(100, current_section.structure_hp + repair_val)
                    turn_log.append(f"🔧 {member.name} repaired {current_section.name} (+{repair_val} HP).")
            
            elif action == "First Aid":
                if member.hp < 100:
                    member.hp = min(100, member.hp + 20)
                    turn_log.append(f"💊 {member.name} applied first aid.")

            elif action == "Turret":
                active_gunners += 1
            elif action == "Evasive Action":
                evasive_maneuvers = True
            elif action == "Lean Mixture":
                lean_mixture = True

        # --- ENVIRONMENT ---
        # Fire Damage
        for section in self.bomber.sections.values():
            if section.is_on_fire:
                dmg = random.randint(5, 15)
                section.structure_hp -= dmg
                turn_log.append(f"🔥 FIRE in {section.name} deals {dmg} damage!")

        # Event
        event_roll = random.randint(1, 100)
        
        if event_roll <= 30:
            turn_log.append("☁️ Sky clear.")
        elif event_roll <= 65:
            turn_log.append("💥 FLAK DETECTED!")
            dmg = random.randint(10, 30)
            if evasive_maneuvers:
                dmg -= 15
                turn_log.append("   (Evasive action reduced damage)")
            
            if dmg > 0:
                hit = random.choice(list(self.bomber.sections.values()))
                hit.structure_hp -= dmg
                turn_log.append(f"   Hit on {hit.name} (-{dmg} HP)")
                if random.random() < 0.3:
                    hit.is_on_fire = True
                    turn_log.append(f"   ⚠️ {hit.name} CAUGHT FIRE!")
        else:
            turn_log.append("⚔️ BANDITS! 12 o'clock high!")
            threat = random.randint(20, 50)
            defense = self.bomber.calculate_defense_score() + (active_gunners * 5)
            
            turn_log.append(f"   Defense: {defense} vs Threat: {threat}")
            final_dmg = threat - defense
            if final_dmg > 0:
                hit = random.choice(list(self.bomber.sections.values()))
                hit.structure_hp -= final_dmg
                turn_log.append(f"   Fighters strafed {hit.name} (-{final_dmg} HP)")
            else:
                turn_log.append("   Bandits repelled!")

        # --- RESOURCES ---
        fuel_cost = 30 if lean_mixture else 50
        self.fuel -= fuel_cost
        self.distance_covered += 20
        self.turn_number += 1
        
        # End Conditions
        for section in self.bomber.sections.values():
            if section.structure_hp <= 0:
                self.is_complete = True
                turn_log.append(f"💀 CRITICAL: {section.name} DESTROYED. PLANE LOST.")
                self.latest_log = turn_log
                return turn_log

        if self.distance_covered >= self.total_distance:
            self.is_complete = True
            self.mission_success = True
            turn_log.append("🏁 TARGET DESTROYED. MISSION SUCCESS.")
        elif self.fuel <= 0:
            self.is_complete = True
            turn_log.append("⛽ OUT OF FUEL. BAILING OUT.")

        self.latest_log = turn_log
        return turn_log