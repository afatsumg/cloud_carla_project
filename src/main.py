import time
import os
import tarfile
from parser import ScenarioParser
from carla_utils import CarlaSimManager
from s3_uploader import upload_to_s3

def run_simulation():
    # Klasörleri hazırla
    os.makedirs("/app/output/camera", exist_ok=True)
    os.makedirs("/app/output/lidar", exist_ok=True)

    parser = ScenarioParser('scenarios/scenario_01.yaml')
    # Docker-compose'daki servis ismini (carla-server) host olarak kullanıyoruz
    sim_manager = CarlaSimManager(host=os.getenv('CARLA_HOST', 'localhost'))

    try:
        sim_manager.setup_world(parser.config['map'], parser.get_weather())
        ego = sim_manager.spawn_ego_vehicle(parser.get_ego_vehicle()['model'])
        
        # Sensörleri tak
        sim_manager.attach_camera()
        sim_manager.attach_lidar()

        # Aracı hareket ettir (Basit bir gaz veriyoruz)
        ego.set_autopilot(True)
        
        print("--- Simülasyon 10 saniye boyunca veri topluyor...")
        time.sleep(10) 

        # Verileri Sıkıştır (S3'e tek parça göndermek daha ucuz ve hızlıdır)
        print("--- Veriler paketleniyor...")
        with tarfile.open("/app/output/results.tar.gz", "w:gz") as tar:
            tar.add("/app/output/camera", arcname="camera")
            tar.add("/app/output/lidar", arcname="lidar")

        # S3'e Yükle
        bucket = os.getenv('AWS_BUCKET_NAME')
        if bucket:
            upload_to_s3("/app/output/results.tar.gz", bucket, f"results_{int(time.time())}.tar.gz")

    except Exception as e:
        print(f"Hata: {e}")
    finally:
        sim_manager.cleanup()

if __name__ == "__main__":
    run_simulation()