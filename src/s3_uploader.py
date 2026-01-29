import boto3
import os
from botocore.exceptions import NoCredentialsError, ClientError

def upload_to_s3(local_file, bucket_name, s3_file):
    """
    Upload file to AWS S3 bucket.
    
    Args:
        local_file: Path to local file
        bucket_name: S3 bucket name
        s3_file: S3 object key (path in bucket)
    
    Returns:
        True if successful, False otherwise
    """
    
    # Verify file exists before attempting upload
    if not os.path.exists(local_file):
        print(f"--- [ERROR] File not found: {local_file}")
        return False

    s3 = boto3.client('s3')

    try:
        file_size = os.path.getsize(local_file) / (1024 * 1024)  # Size in MB
        print(f"--- [AWS S3] Starting upload: {s3_file} ({file_size:.2f} MB)")
        
        s3.upload_file(local_file, bucket_name, s3_file)
        
        print(f"--- [AWS S3] Upload SUCCESSFUL.")
        return True

    except FileNotFoundError:
        print("--- [ERROR] File not found.")
        return False
    except NoCredentialsError:
        print("--- [ERROR] AWS credentials not found.")
        return False
    except ClientError as e:
        print(f"--- [ERROR] AWS Client Error: {e}")
        return False
    except Exception as e:
        print(f"--- [ERROR] Unexpected error: {e}")
        return False