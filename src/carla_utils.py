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
        # Support multiple adversaries and scheduled spawns
        self.adversaries = []  # list of actor instances
        self.adversary_states = []  # parallel list of dicts with behavior/speed/direction
        self.scheduled_spawns = []  # list of {time: float, config: dict}

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
        ego_bp = bp_lib.find(ego_config.get('model')) if ego_config else None
        if not ego_bp:
            ego_bp = bp_lib.find('vehicle.lincoln.mkz_2017') # Fallback

        # Find a spawn point (using the first available one for simplicity in Town01)
        spawn_points = self.world.get_map().get_spawn_points()
        start_tf = spawn_points[0] if spawn_points else carla.Transform()
        
        # Lift it slightly to prevent collision with ground
        start_tf.location.z += 0.5 
        
        self.ego_vehicle = self.world.spawn_actor(ego_bp, start_tf)
        print(f"--- [CARLA] Ego Vehicle spawned: {self.ego_vehicle.type_id}")

        # --- 2. Prepare Adversaries ---
        if not adversary_config:
            return

        # Support a group (count) or a single adversary
        count = int(adversary_config.get('count', 1))
        behavior = adversary_config.get('behavior', 'stationary')

        # If spawn is scheduled (start_time provided), queue them
        if 'start_time' in adversary_config or behavior in ['delayed_crossing', 'sudden_appearance']:
            start_time = float(adversary_config.get('start_time', adversary_config.get('start', 0.0)))
            for i in range(count):
                cfg = dict(adversary_config)
                cfg['_index'] = i
                self.scheduled_spawns.append({'time': start_time, 'config': cfg})
            print(f"--- [CARLA] Scheduled {count} adversary(ies) at t={start_time}s (behavior={behavior}).")
            return

        # Otherwise spawn immediately
        for i in range(count):
            cfg = dict(adversary_config)
            cfg['_index'] = i
            self._spawn_adversary_instance(cfg)

    def _spawn_adversary_instance(self, config):
        """Spawns a single adversary based on the provided config.
        Supports simple patterns: stationary, moving_slow, moving_fast, group staggered, crossing angle/direction.
        """
        bp_lib = self.world.get_blueprint_library()
        adv_type = config.get('type', 'walker.pedestrian.0001')
        adv_bp = bp_lib.find(adv_type)

        # Base spawn: in front of the ego by spawn_dist
        spawn_dist = float(config.get('spawn_dist', 40.0))
        ego_tf = self.ego_vehicle.get_transform()
        fwd = ego_tf.get_forward_vector()
        right = carla.Vector3D(-fwd.y, fwd.x, 0.0)
        ego_loc = self.ego_vehicle.get_location()

        # Lateral offsets for groups or patterns
        idx = int(config.get('_index', 0))
        pattern = config.get('pattern', 'center')
        lateral_offset = 0.0
        if pattern == 'staggered':
            lateral_offset = (idx - 0.5) * 1.0  # 1m stagger
        elif pattern == 'side_by_side':
            lateral_offset = (idx - (config.get('count', 1)-1)/2.0) * 0.9

        # perpendicular offset based on crossing_direction
        crossing_dir = config.get('crossing_direction', 'center')
        if crossing_dir == 'left_to_right':
            lateral = right * -1.0
        elif crossing_dir == 'right_to_left':
            lateral = right * 1.0
        else:
            lateral = carla.Vector3D(0,0,0)

        adv_loc = ego_loc + (fwd * spawn_dist) + (lateral * lateral_offset)
        adv_loc.z += 1.0
        adv_tf = carla.Transform(adv_loc, ego_tf.rotation)

        try:
            adv_actor = self.world.spawn_actor(adv_bp, adv_tf)
        except Exception as e:
            print(f"--- [ERROR] Could not spawn adversary: {e}")
            return

        # Determine movement behavior
        behavior = config.get('behavior', 'stationary')
        speed = config.get('speed', None)
        if speed is None:
            # Defaults (m/s)
            if behavior == 'moving_fast': speed = 4.0
            elif behavior == 'moving_slow': speed = 1.5
            elif behavior == 'moving_medium': speed = 2.5
            else: speed = 0.0

        # Direction vector
        direction = carla.Vector3D(0, 0, 0)
        if behavior.startswith('moving') or behavior in ['delayed_crossing', 'sudden_appearance']:
            # By default move across road (perpendicular to forward)
            angle_deg = float(config.get('angle_deg', 0.0))
            if angle_deg != 0.0:
                # Rotate forward vector by angle around Z
                theta = math.radians(angle_deg)
                direction = carla.Vector3D(
                    fwd.x * math.cos(theta) - fwd.y * math.sin(theta),
                    fwd.x * math.sin(theta) + fwd.y * math.cos(theta),
                    0.0
                )
            elif crossing_dir in ['left_to_right', 'right_to_left']:
                direction = lateral
            else:
                direction = fwd

            # Normalize
            mag = math.sqrt(direction.x**2 + direction.y**2 + direction.z**2)
            if mag > 0:
                direction = carla.Vector3D(direction.x/mag, direction.y/mag, direction.z/mag)

        # Save actor and its state
        self.adversaries.append(adv_actor)
        self.adversary_states.append({
            'actor': adv_actor,
            'behavior': behavior,
            'speed': float(speed),
            'direction': direction,
            'active': True
        })

        print(f"--- [CARLA] Spawned adversary (id={adv_actor.id}) behavior={behavior} speed={speed} m/s")

    def apply_speed(self, speed_kmh):
        """ Applies initial velocity to the ego vehicle """
        if self.ego_vehicle:
            # Convert km/h to m/s
            speed_ms = speed_kmh / 3.6
            # Get the forward vector
            fwd = self.ego_vehicle.get_transform().get_forward_vector()
            velocity = carla.Vector3D(fwd.x * speed_ms, fwd.y * speed_ms, fwd.z * speed_ms)
            try:
                # Vehicles: enable_constant_velocity if available
                self.ego_vehicle.enable_constant_velocity(velocity)
            except Exception:
                # Fallback: set velocity directly
                self.ego_vehicle.set_velocity(velocity)
            print(f"--- [CARLA] Ego speed set to {speed_kmh} km/h")

    def attach_sensors(self):
        """ Dispatches sensor setup based on mode """
        if self.mode == 'sensor':
            self._attach_realistic_camera()
            self._attach_velodyne_lidar()
        else:
            print("--- [INFO] 'Object List' mode selected. No physical sensors attached.")

    def run_simulation_step(self, frame_id):
        """ Called every tick. Handles scheduled spawns and basic per-tick adversary movement."""
        # First, process scheduled spawns if their time has come
        try:
            snapshot = self.world.get_snapshot()
            current_time = snapshot.timestamp.elapsed_seconds
            delta_seconds = snapshot.timestamp.delta_seconds
        except Exception:
            # Fallback: approximate
            current_time = time.time()
            delta_seconds = 1.0 / 10.0

        to_spawn = [s for s in self.scheduled_spawns if s['time'] <= current_time]
        for s in to_spawn:
            cfg = s['config']
            # Support groups: spawn one per scheduled entry
            self._spawn_adversary_instance(cfg)
            self.scheduled_spawns.remove(s)

        # Update moving adversaries
        for state in list(self.adversary_states):
            if not state.get('active'):
                continue
            actor = state['actor']
            if not actor.is_alive:
                state['active'] = False
                continue
            behavior = state['behavior']
            if behavior.startswith('moving') or behavior in ['delayed_crossing', 'sudden_appearance']:
                dir_vec = state.get('direction')
                speed = state.get('speed', 0.0)
                if speed <= 0.0 or (dir_vec.x == 0 and dir_vec.y == 0 and dir_vec.z == 0):
                    continue

                # Move actor forward by speed * delta_seconds (simple kinematic step)
                try:
                    old_loc = actor.get_location()
                    new_loc = carla.Location(
                        x = old_loc.x + dir_vec.x * speed * delta_seconds,
                        y = old_loc.y + dir_vec.y * speed * delta_seconds,
                        z = old_loc.z + dir_vec.z * speed * delta_seconds
                    )
                    new_tf = carla.Transform(new_loc, actor.get_transform().rotation)
                    actor.set_transform(new_tf)
                except Exception as e:
                    # If transform fails, disable that actor
                    print(f"--- [WARN] Could not move adversary id={actor.id}: {e}")
                    state['active'] = False

        # Object list recording
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
                try:
                    sensor.stop()
                except Exception:
                    pass
                try:
                    sensor.destroy()
                except Exception:
                    pass
        self.sensor_list.clear()

        # 2. Ego Vehicle
        if self.ego_vehicle and self.ego_vehicle.is_alive:
            try:
                self.ego_vehicle.destroy()
            except Exception:
                pass

        # 3. All adversaries
        for adv in list(self.adversaries):
            if adv and adv.is_alive:
                try:
                    adv.destroy()
                except Exception:
                    pass
        self.adversaries.clear()
        self.adversary_states.clear()
        self.scheduled_spawns.clear()
            
        print("--- [CARLA] Cleanup finished.")