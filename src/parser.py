import yaml

class ScenarioParser:
    def __init__(self, file_path):
        self.file_path = file_path
        self.config = self._load_yaml()

    def _load_yaml(self):
        with open(self.file_path, 'r') as file:
            return yaml.safe_load(file)

    def get_weather(self):
        return self.config.get('weather', 'ClearNoon')

    def get_sensors(self):
        return self.config.get('sensors', [])

    def get_ego_vehicle(self):
        return self.config.get('ego_vehicle', {})