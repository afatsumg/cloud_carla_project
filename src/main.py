import os
from parser import ScenarioParser
from carla_utils import CarlaSimManager
from s3_uploader import upload_to_s3

def run_simulation():
    scenario_file = 'scenarios/scenario_01.yaml'
    parser = ScenarioParser(scenario_file)
    sim_manager = CarlaSimManager(host='localhost', port=2000)

    try:
        # 1. CARLA'ya Bağlan ve Dünyayı Kur
        sim_manager.setup_world(parser.config['map'], parser.get_weather())
        
        # 2. Aracı Oluştur
        sim_manager.spawn_ego_vehicle(parser.get_ego_vehicle()['model'], "")

        # 3. Veri Topla (Simüle ediyoruz)
        output_file = "/app/output/results.txt"
        with open(output_file, "w") as f:
            f.write(f"Simulasyon {parser.config['scenario_name']} basariyla tamamlandi.")

        # 4. AWS S3'e Yükle (Eğer AWS ortamındaysak)
        if os.getenv('AWS_BUCKET_NAME'):
            upload_to_s3(output_file, os.getenv('AWS_BUCKET_NAME'), "results.txt")

    except Exception as e:
        print(f"Hata oluştu: {e}")
    finally:
        sim_manager.cleanup()

if __name__ == "__main__":
    run_simulation()