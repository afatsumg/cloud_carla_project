import carla
import random
import time

class CarlaSimManager:
    def __init__(self, host='127.0.0.1', port=2000):
        self.client = carla.Client(host, port)
        self.client.set_timeout(10.0)
        self.world = None
        self.ego_vehicle = None
        self.sensor_list = []

    def setup_world(self, map_name, weather_name):
        print(f"--- [CARLA] {map_name} yükleniyor...")
        self.world = self.client.load_world(map_name)
        # Hava durumu ayarı
        weather_preset = getattr(carla.WeatherParameters, weather_name)
        self.world.set_weather(weather_preset)

    def spawn_ego_vehicle(self, model_name, spawn_point_str):
        blueprint = self.world.get_blueprint_library().find(model_name)
        # Basitlik için rastgele bir nokta seçelim (veya spawn_point_str'den parse edilebilir)
        spawn_point = random.choice(self.world.get_map().get_spawn_points())
        self.ego_vehicle = self.world.spawn_actor(blueprint, spawn_point)
        print(f"--- [CARLA] {model_name} oluşturuldu.")
        return self.ego_vehicle

    def cleanup(self):
        print("--- [CARLA] Temizlik yapılıyor...")
        for sensor in self.sensor_list:
            sensor.destroy()
        if self.ego_vehicle:
            self.ego_vehicle.destroy()