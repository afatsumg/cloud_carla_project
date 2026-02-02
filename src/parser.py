import os
import yaml

class ScenarioParser:
    """Simple YAML scenario parser with helpers and light validation."""

    def __init__(self, file_path):
        self.file_path = file_path
        self.config = self._load_yaml() or {}

    def _load_yaml(self):
        with open(self.file_path, 'r') as file:
            return yaml.safe_load(file)

    def get_scenario_name(self):
        return self.config.get('scenario_name', os.path.basename(self.file_path))

    def get_map(self):
        return self.config.get('map', 'Town01')

    def get_simulation_mode(self):
        # 'sensor' or 'object_list'
        return self.config.get('simulation_mode', 'sensor')

    def get_duration(self):
        try:
            return float(self.config.get('duration', 10.0))
        except Exception:
            return 10.0

    def get_weather(self):
        return self.config.get('weather', 'ClearNoon')

    def get_sensors(self):
        return self.config.get('sensors', {})

    def get_ego_vehicle(self):
        return self.config.get('ego_vehicle', {})

    def get_adversary(self):
        return self.config.get('adversary', {})

    def get_metrics(self):
        return self.config.get('metrics', [])

    def validate(self):
        """Return (is_valid:bool, errors:list). Basic presence checks."""
        errors = []
        if 'ego_vehicle' not in self.config:
            errors.append('missing ego_vehicle')
        if 'adversary' not in self.config:
            errors.append('missing adversary')
        if self.get_duration() <= 0:
            errors.append('duration must be > 0')
        return (len(errors) == 0, errors)
