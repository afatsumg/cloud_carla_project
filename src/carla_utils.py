import carla
import os
import time

class CarlaSimManager:
    def __init__(self, host='127.0.0.1', port=2000):
        self.client = carla.Client(host, port)
        self.client.set_timeout(20.0)
        self.world = None
        self.ego_vehicle = None
        self.sensor_list = []
        self.output_path = "/app/output"

    def setup_world(self, map_name, weather_name):
        print(f"--- [CARLA] Loading map {map_name}...")
        try:
            self.world = self.client.load_world(map_name)
            # Use getattr for safe weather enum retrieval
            weather_preset = getattr(carla.WeatherParameters, weather_name, carla.WeatherParameters.ClearNoon)
            self.world.set_weather(weather_preset)
            return True
        except Exception as e:
            print(f"--- [ERROR] Error loading world: {e}")
            return False

    def spawn_ego_vehicle(self, model_name):
        bp_library = self.world.get_blueprint_library()
        blueprint = bp_library.find(model_name)
        
        # If model not found, use fallback vehicle
        if not blueprint:
            print(f"--- [WARNING] {model_name} not found, using 'vehicle.lincoln.mkz_2017'.")
            blueprint = bp_library.find('vehicle.lincoln.mkz_2017')

        spawn_points = self.world.get_map().get_spawn_points()
        spawn_point = spawn_points[0] if spawn_points else carla.Transform()
        
        self.ego_vehicle = self.world.spawn_actor(blueprint, spawn_point)
        print(f"--- [CARLA] Vehicle spawned: {self.ego_vehicle.type_id}")
        return self.ego_vehicle

    def attach_camera(self):
        cam_bp = self.world.get_blueprint_library().find('sensor.camera.rgb')
        cam_bp.set_attribute('image_size_x', '1280')
        cam_bp.set_attribute('image_size_y', '720')
        cam_bp.set_attribute('sensor_tick', '0.1') # 10 FPS (limited to prevent disk overflow)
        
        spawn_point = carla.Transform(carla.Location(x=1.5, z=2.4))
        camera = self.world.spawn_actor(cam_bp, spawn_point, attach_to=self.ego_vehicle)
        
        # Use os.path.join for OS-independent path handling
        camera.listen(lambda image: image.save_to_disk(
            os.path.join(self.output_path, 'camera', f'{image.frame:06d}.png')
        ))
        
        self.sensor_list.append(camera)
        print("--- [SENSOR] Camera attached and recording started.")

    def attach_lidar(self):
        lidar_bp = self.world.get_blueprint_library().find('sensor.lidar.ray_cast')
        lidar_bp.set_attribute('range', '50')
        lidar_bp.set_attribute('channels', '32')
        lidar_bp.set_attribute('points_per_second', '56000')
        lidar_bp.set_attribute('sensor_tick', '0.1') # Synchronized with camera (10 FPS)
        
        spawn_point = carla.Transform(carla.Location(x=0, z=2.4))
        lidar = self.world.spawn_actor(lidar_bp, spawn_point, attach_to=self.ego_vehicle)
        
        lidar.listen(lambda data: data.save_to_disk(
            os.path.join(self.output_path, 'lidar', f'{data.frame:06d}.ply')
        ))
        
        self.sensor_list.append(lidar)
        print("--- [SENSOR] LiDAR attached and recording started.")

    def cleanup(self):
        print("--- [CARLA] Cleaning up...")
        
        # 1. Stop sensors first and destroy them
        for sensor in self.sensor_list:
            if sensor and sensor.is_alive:
                sensor.stop() # Stop data stream
                sensor.destroy()
        
        self.sensor_list.clear() # Clear the list

        # 2. Destroy the vehicle
        if self.ego_vehicle and self.ego_vehicle.is_alive:
            self.ego_vehicle.destroy()
            self.ego_vehicle = None
            
        print("--- [CARLA] All actors cleaned up.")