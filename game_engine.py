import random

class Mission:
    def __init__(self, bomber_obj):
        self.bomber = bomber_obj
        self.target_name = "Ball Bearing Factory at Schweinfurt"
        self.target_desc = "Heavily defended industrial complex. Expect flak belts."
        
        # Mission State
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

        # --- PHASE 1: CREW ACTIONS (The Solution) ---
        active_gunners = 0
        evasive_maneuvers = False
        lean_mixture = False

        # We first process "Maintenance" actions before "Combat"
        for member in self.bomber.crew_roster:
            action = crew_orders.get(member.name, "Passive")
            member.current_assignment = action
            
            # 1. Find which section this crew member is in
            # (We iterate sections to find where they are stationed)
            current_section = None
            for sec in self.bomber.sections.values():
                if member in sec.stationed_crew:
                    current_section = sec
                    break
            
            # 2. Process Actions
            if action == "Repair" and current_section:
                # Extinguish Fire
                if current_section.is_on_fire:
                    current_section.is_on_fire = False
                    turn_log.append(f"🧯 {member.name} put out the fire in {current_section.name}!")
                # Restore HP
                elif current_section.structure_hp < 100:
                    repair_val = random.randint(5, 15) + (member.skill // 2)
                    current_section.structure_hp = min(100, current_section.structure_hp + repair_val)
                    turn_log.append(f"🔧 {member.name} patched up {current_section.name} (+{repair_val} HP).")
            
            elif action == "First Aid":
                # Heals self or others in same section (simplified to self for now)
                if member.hp < 100:
                    heal_val = 20
                    member.hp = min(100, member.hp + heal_val)
                    turn_log.append(f"💊 {member.name} applied first aid (+{heal_val} HP).")

            elif action == "Turret":
                active_gunners += 1
            
            elif action == "Evasive Action":
                evasive_maneuvers = True
            
            elif action == "Lean Mixture":
                lean_mixture = True

        # --- PHASE 2: ENVIRONMENT (The Problem) ---
        # Fires burn BEFORE new damage
        for section in self.bomber.sections.values():
            if section.is_on_fire:
                burn_dmg = random.randint(5, 15)
                section.structure_hp -= burn_dmg
                turn_log.append(f"🔥 FIRE in {section.name} burns for {burn_dmg} damage!")

        # Draw Event
        event_roll = random.randint(1, 100)
        
        if event_roll <= 30:
            turn_log.append("☁️ Sky is clear. Making good time.")
            
        elif event_roll <= 65:
            # --- FLAK ---
            turn_log.append("💥 FLAK BARRAGE!")
            damage_roll = random.randint(10, 30)
            if evasive_maneuvers:
                damage_roll -= 15
                turn_log.append("   (Pilot evasive action reduced damage)")
            
            if damage_roll > 0:
                hit_section = random.choice(list(self.bomber.sections.values()))
                hit_section.structure_hp -= damage_roll
                turn_log.append(f"   Hit on {hit_section.name}! (-{damage_roll} HP)")
                
                # Chance of Fire
                if random.random() < 0.3:
                    hit_section.is_on_fire = True
                    turn_log.append(f"   ⚠️ FUEL LINE RUPTURE! {hit_section.name} is ON FIRE!")
                
                # Chance of Crew Injury in that section
                for crew in hit_section.stationed_crew:
                    if random.random() < 0.4:
                        injury = random.randint(10, 30)
                        crew.hp -= injury
                        turn_log.append(f"   🩸 {crew.name} hit by shrapnel! (-{injury} HP)")

        else:
            # --- FIGHTERS ---
            turn_log.append("⚔️ BANDITS! 12 o'clock high!")
            threat = random.randint(20, 50)
            
            # Calculate Defense
            defense = self.bomber.calculate_defense_score()
            # Bonus for active gunners orders
            defense += (active_gunners * 5)
            
            turn_log.append(f"   Defensive Fire: {defense} vs Threat: {threat}")
            
            final_damage = threat - defense
            if final_damage > 0:
                hit_section = random.choice(list(self.bomber.sections.values()))
                hit_section.structure_hp -= final_damage
                turn_log.append(f"   Fighter bullets riddled {hit_section.name} (-{final_damage} HP)")
            else:
                turn_log.append("   Gunners drove them off!")

        # --- PHASE 3: RESOURCES & END CHECK ---
        fuel_cost = 30 if lean_mixture else 50
        self.fuel -= fuel_cost
        self.distance_covered += 20
        self.turn_number += 1
        
        # Check Defeat (Any section destroyed)
        for section in self.bomber.sections.values():
            if section.structure_hp <= 0:
                self.is_complete = True
                turn_log.append(f"💀 CRITICAL FAILURE: {section.name} has been destroyed. The plane is breaking apart.")
                turn_log.append("MISSION FAILED.")
                self.latest_log = turn_log
                return turn_log

        if self.distance_covered >= self.total_distance:
            self.is_complete = True
            self.mission_success = True
            turn_log.append("🏁 TARGET IN SIGHT. BOMBS AWAY! (Mission Success)")
        elif self.fuel <= 0:
            self.is_complete = True
            turn_log.append("⛽ OUT OF FUEL. Bailing out over enemy territory.")

        self.latest_log = turn_log
        return turn_log
