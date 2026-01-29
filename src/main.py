import time
import os
import tarfile
from parser import ScenarioParser
from carla_utils import CarlaSimManager
from s3_uploader import upload_to_s3

def run_simulation():
    # Prepare directories (This is correct)
    os.makedirs("/app/output/camera", exist_ok=True)
    os.makedirs("/app/output/lidar", exist_ok=True)

    parser = ScenarioParser('scenarios/scenario_01.yaml')
    sim_manager = CarlaSimManager(host=os.getenv('CARLA_HOST', 'localhost'))

    try:
        sim_manager.setup_world(parser.config['map'], parser.get_weather())
        ego = sim_manager.spawn_ego_vehicle(parser.get_ego_vehicle()['model'])
        
        # Attach sensors
        sim_manager.attach_camera()
        sim_manager.attach_lidar()

        # Enable autopilot
        ego.set_autopilot(True)
        
        print("--- Simulation collecting data for 10 seconds...")
        time.sleep(10) 

        # --- CRITICAL CHANGE HERE ---
        # Stop simulation and sensors first to prevent file locking
        # and ensure all data is written to disk
        print("--- Simulation completed, shutting down sensors...")
        sim_manager.cleanup() 
        
        # Buffer time for OS to fully write files to disk (2 seconds)
        time.sleep(2) 
        # --------------------------------

        # Compress data
        print("--- Data is being packaged...")
        
        # Check if folders contain data (useful for debugging)
        cam_count = len(os.listdir("/app/output/camera"))
        lidar_count = len(os.listdir("/app/output/lidar"))
        print(f"--- Report: {cam_count} camera frames, {lidar_count} lidar frames found.")

        if cam_count > 0 or lidar_count > 0:
            tar_path = "/app/output/results.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tar:
                # Use arcname to keep directory structure clean
                tar.add("/app/output/camera", arcname="camera")
                tar.add("/app/output/lidar", arcname="lidar")

            # Upload to S3
            bucket = os.getenv('AWS_BUCKET_NAME')
            if bucket:
                s3_key = f"results_{int(time.time())}.tar.gz"
                print(f"--- Uploading to S3: {bucket}/{s3_key}")
                success = upload_to_s3(tar_path, bucket, s3_key)
                if success:
                    print("--- OPERATION SUCCESSFUL: Data uploaded to cloud.")
                else:
                    print("--- ERROR: S3 upload failed.")
            else:
                print("--- WARNING: AWS_BUCKET_NAME environment variable not found!")
        else:
            print("--- ERROR: No data collected, upload cancelled.")

    except Exception as e:
        print(f"Error: {e}")
        # You can add cleanup here for error cases
        # or use a finally block, but be careful not to call cleanup twice
        # since it's already called above (managing it in try-except is safer for now).

if __name__ == "__main__":
    run_simulation()