import carla
import os
import json
import math
import time

class CarlaSimManager:
    def __init__(self, mode='sensor', host='127.0.0.1', port=2000):
        self.client = carla.Client(host, port)
        self.client.set_timeout(30.0)
        self.world = None
        self.ego_vehicle = None
        self.adversary = None
        self.sensor_list = []
        self.output_path = "/app/output"
        self.mode = mode # 'sensor' or 'object_list'

    def setup_world(self, map_name, weather_name):
        print(f"--- [CARLA] Loading map: {map_name} (Mode: {self.mode})...")
        try:
            self.world = self.client.load_world(map_name)
            # Safe enum retrieval
            weather_preset = getattr(carla.WeatherParameters, weather_name, carla.WeatherParameters.ClearNoon)
            self.world.set_weather(weather_preset)
            
            # Wait for the world to settle
            self.world.tick()
            return True
        except Exception as e:
            print(f"--- [ERROR] Failed to load world: {e}")
            return False

    def spawn_actors(self, ego_config, adversary_config):
        bp_lib = self.world.get_blueprint_library()
        
        # --- 1. Spawn Ego Vehicle ---
        ego_bp = bp_lib.find(ego_config['model'])
        if not ego_bp:
            ego_bp = bp_lib.find('vehicle.lincoln.mkz_2017') # Fallback

        # Find a spawn point (using the first available one for simplicity in Town01)
        spawn_points = self.world.get_map().get_spawn_points()
        start_tf = spawn_points[0] if spawn_points else carla.Transform()
        
        # Lift it slightly to prevent collision with ground
        start_tf.location.z += 0.5 
        
        self.ego_vehicle = self.world.spawn_actor(ego_bp, start_tf)
        print(f"--- [CARLA] Ego Vehicle spawned: {self.ego_vehicle.type_id}")

        # --- 2. Spawn Adversary (Relative to Ego) ---
        if adversary_config:
            adv_bp = bp_lib.find(adversary_config['type'])
            
            # Calculate position: X meters in front of the car
            # Get Forward Vector
            fwd_vec = self.ego_vehicle.get_transform().get_forward_vector()
            ego_loc = self.ego_vehicle.get_location()
            
            dist = adversary_config.get('spawn_dist', 40.0)
            
            # Vector addition
            adv_loc = ego_loc + (fwd_vec * dist)
            adv_loc.z += 1.0 # Spawn slightly in the air to settle physics
            
            adv_tf = carla.Transform(adv_loc, self.ego_vehicle.get_transform().rotation)
            
            self.adversary = self.world.spawn_actor(adv_bp, adv_tf)
            print(f"--- [CARLA] Adversary spawned {dist}m ahead.")

    def apply_speed(self, speed_kmh):
        """ Applies initial velocity to the ego vehicle """
        if self.ego_vehicle:
            # Convert km/h to m/s
            speed_ms = speed_kmh / 3.6
            # Get the forward vector
            fwd = self.ego_vehicle.get_transform().get_forward_vector()
            velocity = carla.Vector3D(fwd.x * speed_ms, fwd.y * speed_ms, fwd.z * speed_ms)
            self.ego_vehicle.enable_constant_velocity(velocity)
            print(f"--- [CARLA] Ego speed set to {speed_kmh} km/h")

    def attach_sensors(self):
        """ Dispatches sensor setup based on mode """
        if self.mode == 'sensor':
            self._attach_realistic_camera()
            self._attach_velodyne_lidar()
        else:
            print("--- [INFO] 'Object List' mode selected. No physical sensors attached.")

    def run_simulation_step(self, frame_id):
        """ Called every tick. Handles Object List recording. """
        if self.mode == 'object_list':
            self._save_object_list(frame_id)

    def _save_object_list(self, frame_id):
        """ Generates Ground Truth JSON data for all nearby actors """
        objects_data = []
        
        # Get all relevant actors
        vehicles = self.world.get_actors().filter('vehicle.*')
        walkers = self.world.get_actors().filter('walker.*')
        all_actors = list(vehicles) + list(walkers)
        
        ego_loc = self.ego_vehicle.get_location()

        for actor in all_actors:
            if actor.id == self.ego_vehicle.id:
                continue 

            dist = actor.get_location().distance(ego_loc)
            
            # Only record actors within 100m
            if dist > 100:
                continue

            # Calculate Velocity Scalar
            vel_vec = actor.get_velocity()
            speed = math.sqrt(vel_vec.x**2 + vel_vec.y**2 + vel_vec.z**2)

            obj_info = {
                "id": actor.id,
                "type": actor.type_id,
                "distance": round(dist, 2),
                "speed_ms": round(speed, 2),
                "location": {
                    "x": round(actor.get_location().x, 2),
                    "y": round(actor.get_location().y, 2),
                    "z": round(actor.get_location().z, 2)
                }
            }
            objects_data.append(obj_info)

        # Save to JSON
        folder = os.path.join(self.output_path, 'object_list')
        os.makedirs(folder, exist_ok=True)
        
        file_path = os.path.join(folder, f'{frame_id:06d}.json')
        with open(file_path, 'w') as f:
            json.dump(objects_data, f, indent=2)

    def _attach_realistic_camera(self):
        bp = self.world.get_blueprint_library().find('sensor.camera.rgb')
        
        # Automotive Grade Settings
        bp.set_attribute('image_size_x', '1920')
        bp.set_attribute('image_size_y', '1080')
        bp.set_attribute('fov', '110')
        bp.set_attribute('shutter_speed', '60.0') # Motion blur
        bp.set_attribute('chromatic_aberration_intensity', '0.5')
        bp.set_attribute('bloom_intensity', '0.675')
        bp.set_attribute('sensor_tick', '0.1') # 10 FPS
        
        spawn_point = carla.Transform(carla.Location(x=1.5, z=2.4))
        cam = self.world.spawn_actor(bp, spawn_point, attach_to=self.ego_vehicle)
        
        cam.listen(lambda image: image.save_to_disk(
            os.path.join(self.output_path, 'camera', f'{image.frame:06d}.png')
        ))
        self.sensor_list.append(cam)
        print("--- [SENSOR] Realistic Camera attached.")

    def _attach_velodyne_lidar(self):
        bp = self.world.get_blueprint_library().find('sensor.lidar.ray_cast')
        
        # Velodyne HDL-64E Specs
        bp.set_attribute('channels', '64')
        bp.set_attribute('points_per_second', '1300000')
        bp.set_attribute('rotation_frequency', '10')
        bp.set_attribute('range', '100')
        bp.set_attribute('upper_fov', '2.0')
        bp.set_attribute('lower_fov', '-24.8')
        bp.set_attribute('noise_stddev', '0.02') # Realism
        bp.set_attribute('sensor_tick', '0.1')
        
        spawn_point = carla.Transform(carla.Location(x=0, z=1.8))
        lidar = self.world.spawn_actor(bp, spawn_point, attach_to=self.ego_vehicle)
        
        lidar.listen(lambda data: data.save_to_disk(
            os.path.join(self.output_path, 'lidar', f'{data.frame:06d}.ply')
        ))
        self.sensor_list.append(lidar)
        print("--- [SENSOR] Velodyne LiDAR attached.")

    def cleanup(self):
        print("--- [CARLA] Cleaning up...")
        
        # 1. Sensors
        for sensor in self.sensor_list:
            if sensor and sensor.is_alive:
                sensor.stop()
                sensor.destroy()
        self.sensor_list.clear()

        # 2. Ego Vehicle
        if self.ego_vehicle and self.ego_vehicle.is_alive:
            self.ego_vehicle.destroy()

        # 3. Adversary
        if self.adversary and self.adversary.is_alive:
            self.adversary.destroy()
            
        print("--- [CARLA] Cleanup finished.")