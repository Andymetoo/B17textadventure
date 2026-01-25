import random

class Mission:
    def __init__(self, bomber_obj):
        self.bomber = bomber_obj
        self.target_name = "Ball Bearing Factory at Schweinfurt"
        self.total_distance = 400  # 20 miles per turn = 20 turns
        self.distance_covered = 0
        self.fuel = 1400  # Increased fuel for 4 engines
        self.turn_number = 1
        self.is_complete = False
        self.mission_success = False
        self.latest_log = ["Mission Start. Formation assembled at 20,000 feet."]

    def resolve_turn(self, crew_orders):
        turn_log = []
        turn_log.append(f"--- Turn {self.turn_number} (Mile {self.distance_covered}) ---")

        active_gunners = 0
        evasive_maneuvers = False
        lean_mixture = False

        # --- PHASE 0: MOVEMENT (Happens before actions) ---
        for member in self.bomber.crew_roster:
            order = crew_orders.get(member.name, "Passive")
            
            # Handle Movement
            if order.startswith("Move to "):
                target_section_name = order.replace("Move to ", "")
                current_sec = self.bomber.get_crew_section(member)
                target_sec = self.bomber.sections.get(target_section_name)
                
                if current_sec and target_sec and current_sec != target_sec:
                    current_sec.remove_crew(member)
                    target_sec.add_crew(member)
                    turn_log.append(f"🏃 {member.name} moved to {target_sec.name}.")
                
                # If you move, you can't do anything else this turn
                member.current_assignment = "Passive"

        # --- PHASE 1: CREW ACTIONS ---
        for member in self.bomber.crew_roster:
            order = crew_orders.get(member.name, "Passive")
            if order.startswith("Move to "): continue # Skip movers

            member.current_assignment = order
            current_section = self.bomber.get_crew_section(member)
            
            # 1. REPAIR / FIREFIGHTING
            if order == "Repair" and current_section:
                if current_section.is_on_fire:
                    # Firefighting skill check
                    if random.randint(1, 10) + member.skill > 8:
                        current_section.is_on_fire = False
                        turn_log.append(f"🧯 {member.name} EXTINGUISHED the fire in {current_section.name}!")
                    else:
                        turn_log.append(f"🧯 {member.name} fought the fire in {current_section.name} but it rages on.")
                
                elif current_section.structure_hp < 100:
                    repair_val = random.randint(5, 10) + (member.skill // 2)
                    current_section.structure_hp = min(100, current_section.structure_hp + repair_val)
                    turn_log.append(f"🔧 {member.name} repaired {current_section.name} (+{repair_val} HP).")
            
            # 2. FIRST AID
            elif order == "First Aid":
                # Find injured people in same section
                for patient in current_section.stationed_crew:
                    if patient.hp < 100:
                        heal_val = 15 + member.skill
                        patient.hp = min(100, patient.hp + heal_val)
                        turn_log.append(f"✚ {member.name} treated {patient.name} (+{heal_val} HP).")
                        break # Only heal one person per turn

            # 3. COMBAT & SHIP STUFF
            elif order == "Turret":
                active_gunners += 1
            elif order == "Evasive Action":
                evasive_maneuvers = True
            elif order == "Lean Mixture":
                lean_mixture = True

        # --- PHASE 2: ENVIRONMENT ---
        # Fire Damage (HAPPENS BEFORE FLAK)
        for section in self.bomber.sections.values():
            if section.is_on_fire:
                dmg = random.randint(10, 20)
                section.structure_hp -= dmg
                turn_log.append(f"🔥 FIRE in {section.name} burns for {dmg} damage!")
                if section.structure_hp <= 0:
                     turn_log.append(f"💥 {section.name} HAS COLLAPSED FROM FIRE DAMAGE!")

        # Event Generation
        event_roll = random.randint(1, 100)
        
        # 30% Clear, 30% Flak, 40% Fighters
        if event_roll <= 30:
            turn_log.append("☁️ Cruising at altitude. No contacts.")
            
        elif event_roll <= 60:
            # FLAK
            turn_log.append("💥 FLAK BARRAGE DETECTED!")
            base_dmg = random.randint(15, 35)
            
            if evasive_maneuvers:
                base_dmg -= 15
                turn_log.append("   (Evasive action reduced flak accuracy)")
            
            if base_dmg > 0:
                # Flak hits random section
                hit_section = random.choice(list(self.bomber.sections.values()))
                hit_section.structure_hp -= base_dmg
                turn_log.append(f"   Flak burst hit {hit_section.name} (-{base_dmg} HP)")
                
                # Shrapnel hits crew?
                if hit_section.stationed_crew:
                    for crew in hit_section.stationed_crew:
                        if random.random() < 0.3: # 30% chance per person
                            injury = random.randint(10, 40)
                            crew.hp -= injury
                            turn_log.append(f"   🩸 {crew.name} hit by shrapnel! (-{injury} HP)")
                
                # Fire Chance
                if random.random() < 0.25:
                    hit_section.is_on_fire = True
                    turn_log.append(f"   ⚠️ FUEL LEAK! {hit_section.name} IS ON FIRE!")

        else:
            # FIGHTERS
            turn_log.append("⚔️ BANDITS! ME-109s at 12 o'clock!")
            threat = random.randint(30, 80)
            
            defense = self.bomber.calculate_defense_score()
            # Bonus for having 'Turret' assignments
            defense += (active_gunners * 5)
            
            turn_log.append(f"   Defense Score: {defense} vs Threat: {threat}")
            
            damage = threat - defense
            if damage > 0:
                hit_section = random.choice(list(self.bomber.sections.values()))
                hit_section.structure_hp -= damage
                turn_log.append(f"   Fighters strafed {hit_section.name} (-{damage} HP)")
            else:
                turn_log.append("   Gunners drove them off! No damage.")

        # --- PHASE 3: END CHECK ---
        fuel_cost = 25 if lean_mixture else 45
        self.fuel -= fuel_cost
        self.distance_covered += 20
        self.turn_number += 1
        
        # Check Structural Failure
        for section in self.bomber.sections.values():
            if section.structure_hp <= 0:
                self.is_complete = True
                turn_log.append(f"💀 CRITICAL FAILURE: {section.name} SHEARED OFF. PLANE LOST.")
                self.latest_log = turn_log
                return turn_log

        # Check Mission End
        if self.distance_covered >= self.total_distance:
            self.is_complete = True
            
            # FINAL BOMB RUN CHECK
            nose_section = self.bomber.sections["Nose"]
            bombardier_present = False
            for c in nose_section.stationed_crew:
                if c.role == "Bombardier" and c.hp > 0:
                    bombardier_present = True
            
            if bombardier_present:
                self.mission_success = True
                turn_log.append("🎯 BOMBARDIER ON SIGHT. BOMBS AWAY! TARGET DESTROYED.")
            else:
                self.mission_success = False
                turn_log.append("❌ BOMBARDIER NOT IN NOSE OR INCAPACITATED. BOMBS MISSED THE TARGET.")
                
        elif self.fuel <= 0:
            self.is_complete = True
            turn_log.append("⛽ OUT OF FUEL. BAILING OUT OVER ENEMY TERRITORY.")

        self.latest_log = turn_log
        return turn_log