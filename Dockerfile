# 1. Base image: lightweight Python 3.9
FROM python:3.9-slim

# 2. System dependencies installation (required for OpenCV and CARLA API)
RUN apt-get update && apt-get install -y \
    libpng-dev \
    libjpeg-dev \
    libtiff-dev \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Set working directory
WORKDIR /app

# 4. Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy project files
COPY src/ ./src/
COPY scenarios/ ./scenarios/

# 6. Create output directory (staging area before S3 upload)
RUN mkdir /app/output

# 7. Run main simulation
CMD ["python", "src/main.py"]