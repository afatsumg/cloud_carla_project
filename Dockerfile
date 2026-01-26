# 1. Temel imaj olarak hafif bir Python imajı seçiyoruz
FROM python:3.9-slim

# 2. Sistem bağımlılıklarını kur (OpenCV ve CARLA API için gerekli kütüphaneler)
RUN apt-get update && apt-get install -y \
    libpng-dev \
    libjpeg-dev \
    libtiff-dev \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Çalışma dizinini ayarla
WORKDIR /app

# 4. Bağımlılıkları kopyala ve kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Proje dosyalarını içeri aktar
COPY src/ ./src/
COPY scenarios/ ./scenarios/

# 6. Çıkış verileri için bir klasör oluştur (S3'e gitmeden önceki durak)
RUN mkdir /app/output

# 7. Kodumuzu çalıştıralım
CMD ["python", "src/main.py"]