import boto3
import os

def upload_to_s3(local_file, bucket_name, s3_file):
    s3 = boto3.client('s3')
    try:
        s3.upload_file(local_file, bucket_name, s3_file)
        print(f"--- [AWS S3] {s3_file} başarıyla yüklendi.")
        return True
    except Exception as e:
        print(f"--- [AWS S3] Hata: {e}")
        return False