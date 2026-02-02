import math
import carla

class MetricCalculator:
    def __init__(self):
        # Registry: Maps YAML strings to function names
        self.metric_map = {
            "distance_to_adversary": self._calc_distance,
            "ego_speed": self._calc_speed,
            "ttc": self._calc_ttc,
            "collision": self._check_collision,
            "brake_applied": self._calc_brake_applied,
            "detection_confidence": self._calc_detection_confidence,
            "acceleration": self._calc_acceleration
        }

        # Internal state for temporal metrics
        self.prev_ego_speed = None
        self.prev_time = None


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

    def _get_nearest_adversary(self, sim):
        # Support both legacy 'adversary' and new 'adversaries' lists
        ego = sim.ego_vehicle
        if not ego:
            return (None, None)

        ego_loc = ego.get_location()

        # Prefer sim.adversaries list
        candidates = []
        if hasattr(sim, 'adversaries') and sim.adversaries:
            candidates = sim.adversaries
        elif hasattr(sim, 'adversary') and sim.adversary:
            candidates = [sim.adversary]

        nearest = None
        nearest_dist = None
        for a in candidates:
            try:
                d = a.get_location().distance(ego_loc)
            except Exception:
                continue
            if nearest is None or d < nearest_dist:
                nearest = a
                nearest_dist = d
        return (nearest, nearest_dist)

    def _calc_distance(self, sim):
        adv, dist = self._get_nearest_adversary(sim)
        if adv is None or dist is None:
            return None
        return round(dist, 2)

    def _calc_speed(self, sim):
        if not sim.ego_vehicle:
            return 0.0
        
        vel = sim.ego_vehicle.get_velocity()
        speed_ms = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2)
        return round(speed_ms * 3.6, 2) # Return km/h

    def _calc_ttc(self, sim):
        """ Time To Collision computed against nearest adversary.
        Uses projection of relative velocity onto the line connecting ego->adv. Returns seconds or None.
        """
        ego = sim.ego_vehicle
        if not ego:
            return None

        adv, dist = self._get_nearest_adversary(sim)
        if not adv or dist is None:
            return None

        # positions and velocities
        ego_loc = ego.get_location()
        adv_loc = adv.get_location()
        v_ego = ego.get_velocity()
        v_adv = adv.get_velocity()

        # vector from ego to adv
        dx = adv_loc.x - ego_loc.x
        dy = adv_loc.y - ego_loc.y
        mag = math.sqrt(dx*dx + dy*dy)
        if mag < 0.001:
            return 0.0
        ux, uy = dx/mag, dy/mag

        # relative velocity along the line (positive if closing)
        rel_vx = v_ego.x - v_adv.x
        rel_vy = v_ego.y - v_adv.y
        rel_along = rel_vx * ux + rel_vy * uy

        # if rel_along <= 0 => not closing
        if rel_along <= 0.1:
            return None

        ttc = dist / rel_along
        return round(ttc, 2)


    def _calc_acceleration(self, sim):
        if not sim.ego_vehicle:
            return 0.0
        acc = sim.ego_vehicle.get_acceleration()
        return round(math.sqrt(acc.x**2 + acc.y**2), 2)

    def _check_collision(self, sim):
        adv, dist = self._get_nearest_adversary(sim)
        if adv is None or dist is None:
            return False
        return dist < 1.5

    def _calc_brake_applied(self, sim):
        """Detect braking by negative longitudinal acceleration along vehicle forward vector."""
        ego = sim.ego_vehicle
        if not ego:
            return None
        try:
            acc = ego.get_acceleration()
            fwd = ego.get_transform().get_forward_vector()
            long_acc = acc.x * fwd.x + acc.y * fwd.y + acc.z * fwd.z
            # threshold: -1.0 m/s^2 considered braking
            return bool(long_acc < -1.0)
        except Exception:
            return None

    def _calc_detection_confidence(self, sim):
        """Heuristic confidence based on nearest adversary distance. Only meaningful in 'sensor' mode."""
        if getattr(sim, 'mode', 'sensor') != 'sensor':
            return None
        adv, dist = self._get_nearest_adversary(sim)
        if adv is None or dist is None:
            return None
        # Simple falloff: 1.0 at 0m -> 0.0 at >=100m
        conf = max(0.0, 1.0 - (dist / 100.0))
        return round(conf, 2)
