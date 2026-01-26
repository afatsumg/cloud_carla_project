import carla
import os

class CarlaSimManager:
    def __init__(self, host='127.0.0.1', port=2000):
        self.client = carla.Client(host, port)
        self.client.set_timeout(20.0)
        self.world = None
        self.ego_vehicle = None
        self.sensor_list = []
        self.output_path = "/app/output"

    def setup_world(self, map_name, weather_name):
        print(f"--- [CARLA] {map_name} yükleniyor...")
        self.world = self.client.load_world(map_name)
        weather_preset = getattr(carla.WeatherParameters, weather_name)
        self.world.set_weather(weather_preset)

    def spawn_ego_vehicle(self, model_name):
        blueprint = self.world.get_blueprint_library().find(model_name)
        spawn_point = self.world.get_map().get_spawn_points()[0] # İlk müsait noktaya koy
        self.ego_vehicle = self.world.spawn_actor(blueprint, spawn_point)
        return self.ego_vehicle

    def attach_camera(self):
        cam_bp = self.world.get_blueprint_library().find('sensor.camera.rgb')
        cam_bp.set_attribute('image_size_x', '1280')
        cam_bp.set_attribute('image_size_y', '720')
        
        # Araca göre konumu (ön tampon üstü)
        spawn_point = carla.Transform(carla.Location(x=1.5, z=2.4))
        camera = self.world.spawn_actor(cam_bp, spawn_point, attach_to=self.ego_vehicle)
        
        # Veri geldiğinde yapılacak işlem: Kaydet
        camera.listen(lambda image: image.save_to_disk(os.path.join(self.output_path, 'camera/%06d.png' % image.frame)))
        self.sensor_list.append(camera)
        print("--- [SENSÖR] Kamera bağlandı.")

    def attach_lidar(self):
        lidar_bp = self.world.get_blueprint_library().find('sensor.lidar.ray_cast')
        lidar_bp.set_attribute('range', '50')
        lidar_bp.set_attribute('channels', '32')
        
        spawn_point = carla.Transform(carla.Location(x=0, z=2.4))
        lidar = self.world.spawn_actor(lidar_bp, spawn_point, attach_to=self.ego_vehicle)
        
        # LiDAR verisini kaydet (.ply formatında)
        lidar.listen(lambda data: data.save_to_disk(os.path.join(self.output_path, 'lidar/%06d.ply' % data.frame)))
        self.sensor_list.append(lidar)
        print("--- [SENSÖR] LiDAR bağlandı.")

    def cleanup(self):
        print("--- [CARLA] Temizlik yapılıyor...")
        for sensor in self.sensor_list:
            sensor.destroy()
        if self.ego_vehicle:
            self.ego_vehicle.destroy()