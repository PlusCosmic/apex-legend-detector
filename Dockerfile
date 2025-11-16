FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxext6 libxrender-dev \
    libgomp1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apex-legend-detector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apex-legend-detector/detector.py apex-legend-detector/worker.py ./
COPY apex-legend-detector/portraits/ /app/portraits/

CMD ["python", "-u", "worker.py"]