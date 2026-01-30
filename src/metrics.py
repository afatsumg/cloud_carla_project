import math
import carla

class MetricCalculator:
    def __init__(self):
        # Registry: Maps YAML strings to function names
        self.metric_map = {
            "distance_to_adversary": self._calc_distance,
            "ego_speed": self._calc_speed,
            "ttc": self._calc_ttc,
            "collision_sensor": self._check_collision,
            "acceleration": self._calc_acceleration
        }

    def compute(self, metric_names, sim_manager):
        """
        Computes only the metrics listed in the YAML configuration.
        Returns a dictionary: {"ttc": 2.4, "ego_speed": 40.5, ...}
        """
        results = {}
        for name in metric_names:
            if name in self.metric_map:
                try:
                    # Call the function passing the simulation manager
                    results[name] = self.metric_map[name](sim_manager)
                except Exception as e:
                    results[name] = None # Handle errors gracefully
            else:
                print(f"--- [WARNING] Metric '{name}' not found in registry.")
        return results

    # --- METRIC IMPLEMENTATIONS ---

    def _calc_distance(self, sim):
        if not sim.ego_vehicle or not sim.adversary:
            return -1.0
        
        loc1 = sim.ego_vehicle.get_location()
        loc2 = sim.adversary.get_location()
        return round(loc1.distance(loc2), 2)

    def _calc_speed(self, sim):
        if not sim.ego_vehicle:
            return 0.0
        
        vel = sim.ego_vehicle.get_velocity()
        speed_ms = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2)
        return round(speed_ms * 3.6, 2) # Return km/h

    def _calc_ttc(self, sim):
        """ Time To Collision = Distance / Relative Speed """
        if not sim.ego_vehicle or not sim.adversary:
            return 999.0
        
        dist = self._calc_distance(sim)
        
        # Ego Speed
        v1 = sim.ego_vehicle.get_velocity()
        s1 = math.sqrt(v1.x**2 + v1.y**2)
        
        # Adversary Speed (if moving)
        v2 = sim.adversary.get_velocity()
        s2 = math.sqrt(v2.x**2 + v2.y**2)
        
        # Relative Speed (Assuming head-on or chasing)
        # Simplified logic: If getting closer, relative speed is positive
        rel_speed = s1 - s2 
        
        if rel_speed > 0.1:
            return round(dist / rel_speed, 2)
        else:
            return 999.0 # Safe / Moving away

    def _calc_acceleration(self, sim):
        if not sim.ego_vehicle:
            return 0.0
        acc = sim.ego_vehicle.get_acceleration()
        return round(math.sqrt(acc.x**2 + acc.y**2), 2)

    def _check_collision(self, sim):
        # This is a simplified check based on distance for now.
        # A real implementation would use a collision sensor callback.
        dist = self._calc_distance(sim)
        return dist < 1.5 and dist != -1.0