FROM python:3.9-slim-bullseye

# Install system dependencies for OpenCV, audio, and Bluetooth
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libasound2 \
    libsdl2-mixer-2.0-0 \
    libsdl2-2.0-0 \
    alsa-utils \
    pulseaudio \
    pulseaudio-module-bluetooth \
    bluez \
    dbus \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/theme-song

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download OpenVINO face models at build time
COPY setup_models.sh .
RUN bash setup_models.sh && rm -f setup_models.sh

# Copy application code
COPY config.yaml .
COPY entrypoint.sh .
COPY src/ src/
RUN chmod +x entrypoint.sh

# Create directories for user data (mounted at runtime)
RUN mkdir -p songs data/faces photos models

ENV PYTHONUNBUFFERED=1

CMD ["./entrypoint.sh"]
