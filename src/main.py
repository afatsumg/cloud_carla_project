import time
import os
import yaml
import tarfile
import json
from carla_utils import CarlaSimManager
from metrics import MetricCalculator
from s3_uploader import upload_to_s3

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def run_simulation():
    # --- 1. CONFIGURATION LOAD ---
    # Default scenario if not specified in Environment Variables
    default_scenario = 'scenario_01.yaml'
    scenario_file = os.getenv('SCENARIO_FILE', default_scenario)
    
    # Construct full path (files are inside scenarios/ folder)
    config_path = os.path.join('scenarios', scenario_file)

    print(f"--- [MAIN] Loading Configuration: {config_path}")

    if not os.path.exists(config_path):
        print(f"--- [ERROR] Config file not found: {config_path}")
        return
    
    config = load_config(config_path)
    print(f"--- [MAIN] Scenario Name: {config.get('scenario_name')}")
    print(f"--- [MAIN] Simulation Mode: {config.get('simulation_mode')}")

    # --- 2. SETUP DIRECTORIES ---
    output_dir = "/app/output"
    os.makedirs(os.path.join(output_dir, "camera"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "lidar"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "object_list"), exist_ok=True)

    # --- 3. INITIALIZE MANAGERS ---
    # Pass the mode from YAML to the Manager
    sim_mode = config.get('simulation_mode', 'sensor')
    host = os.getenv('CARLA_HOST', 'localhost')
    
    sim = CarlaSimManager(mode=sim_mode, host=host)
    
    # Initialize Metric Calculator
    metric_calculator = MetricCalculator()
    # Get active metrics list from YAML
    active_metrics = config.get('metrics', [])

    metrics_log = []

    try:
        # --- 4. SETUP WORLD & ACTORS ---
        if not sim.setup_world(config['map'], config['weather']):
            print("--- [ERROR] World setup failed.")
            return
            
        sim.spawn_actors(config['ego_vehicle'], config['adversary'])
        
        # Attach sensors (Camera/Lidar) OR just prepare Object List recorder
        sim.attach_sensors()

        # Apply initial speed to Ego Vehicle
        sim.apply_speed(config['ego_vehicle']['target_speed'])

        # --- 5. SIMULATION LOOP ---
        duration = config.get('duration', 10.0)
        fps = 10
        total_frames = int(duration * fps)
        
        print(f"--- [MAIN] Running simulation for {duration} seconds...")

        for frame in range(total_frames):
            # Advance simulation
            sim.world.tick()
            
            # Record Object List (Ground Truth) if enabled
            sim.run_simulation_step(frame)
            
            # --- CALCULATE METRICS ---
            # Compute only what is requested in YAML
            current_metrics = metric_calculator.compute(active_metrics, sim)
            
            # Add metadata
            current_metrics['timestamp'] = time.time()
            current_metrics['frame'] = frame
            
            metrics_log.append(current_metrics)
            # -------------------------

            # Optional: Real-time console log for debugging
            if frame % 10 == 0:
                dist = current_metrics.get('distance_to_adversary', 'N/A')
                ttc = current_metrics.get('ttc', 'N/A')
                print(f"Frame {frame}: Dist={dist}m, TTC={ttc}s")

            time.sleep(1.0 / fps) # Sync with real time

        # --- 6. SAVE RESULTS ---
        # Save Metrics to JSON
        metrics_file = os.path.join(output_dir, 'metrics.json')
        with open(metrics_file, 'w') as f:
            json.dump(metrics_log, f, indent=2)
        print(f"--- [MAIN] Metrics saved to {metrics_file}")

    except Exception as e:
        print(f"--- [FATAL ERROR] Simulation crashed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # --- 7. CLEANUP & UPLOAD ---
        print("--- [MAIN] Stopping simulation & Cleaning up...")
        sim.cleanup()
        
        # Wait for disk I/O flush
        time.sleep(2) 

        # Compress Output Directory
        tar_path = "/app/output/results.tar.gz"
        print("--- [MAIN] Compressing data...")
        try:
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(output_dir, arcname="output")
        except Exception as e:
            print(f"--- [ERROR] Compression failed: {e}")

        # Upload to S3
        bucket = os.getenv('AWS_BUCKET_NAME')
        if bucket:
            scenario_name = config.get('scenario_name', 'unknown')
            s3_key = f"results_{scenario_name}_{int(time.time())}.tar.gz"
            
            print(f"--- [MAIN] Uploading to S3 Bucket: {bucket}")
            success = upload_to_s3(tar_path, bucket, s3_key)
            
            if success:
                print("--- [SUCCESS] Data successfully stored in cloud.")
            else:
                print("--- [ERROR] Upload failed.")
        else:
            print("--- [WARNING] AWS_BUCKET_NAME not set. Upload skipped.")

if __name__ == "__main__":
    run_simulation()