---
name: azure-percept-docker-patterns
description: >
  Docker patterns and gotchas specific to Azure Percept DK (Docker 19.03 on CBL-Mariner ARM64).
  Covers image building, file transfer, quoting issues, and container management.
  Apply when building or running Docker containers on the Percept DK.
---

# Azure Percept DK — Docker Patterns & Gotchas

## Base Image
Use `python:3.9-slim-bullseye` — works on aarch64, has working pip and package repos.

## Dockerfile Pattern
```dockerfile
FROM python:3.9-slim-bullseye

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg pulseaudio bluez libglib2.0-0 dbus && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY config.yaml entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
```

## Building on Device
```bash
# Copy project to device first
scp -r . <YOUR_USER>@<DEVICE_IP>:/opt/theme-song/

# Build (slow on ARM64, ~10-15 min)
ssh <YOUR_USER>@<DEVICE_IP> \
  "cd /opt/theme-song && sudo docker build -t theme-song ."
```

## Critical Gotchas

### 1. Windows Line Endings (\r)
Scripts transferred from Windows will have `\r` causing `bash: \r: command not found`.
**Fix**: Add to Dockerfile or run before execution:
```bash
sed -i "s/\r//" entrypoint.sh
```

### 2. Nested Quoting Hell
PowerShell → SSH → Docker → bash/python quoting breaks constantly.
**Fix**: Write scripts to files, SCP them to the device, run them:
```powershell
$script | Set-Content -Path "local_script.py" -Encoding utf8
scp local_script.py <YOUR_USER>@<DEVICE_IP>:/opt/theme-song/src/
ssh <YOUR_USER>@<DEVICE_IP> "sudo docker run --rm -v /opt/theme-song/src:/app/src theme-song python3 src/local_script.py"
```

### 3. SSL Certificate Issues
`wget` fails inside containers on this device. Use `curl -sk` instead:
```bash
curl -sk -o model.xml https://storage.openvinotoolkit.org/...
```

### 4. overlay2 Corruption
If Docker breaks with overlay2 errors:
```bash
sudo systemctl stop docker
sudo rm -rf /var/lib/docker/overlay2 /var/lib/docker/image /var/lib/docker/containers
sudo systemctl start docker
# All images and containers are lost — must rebuild
```

### 5. Disk Space
Only 10.5 GB on `/var`. Monitor with `df -h /var`. Prune unused images:
```bash
sudo docker system prune -f
```

## Container Patterns

### Run with Host Network + Privileged (for USB/BT access)
```bash
sudo docker run --rm -d --privileged --network host \
  --name my-container theme-song
```

### Mount Persistent Volumes
```bash
sudo docker run --rm -d --network host \
  -v /opt/theme-song/models:/app/models \
  -v /opt/theme-song/data:/app/data \
  -v /opt/theme-song/songs:/app/songs \
  --name theme-song-app theme-song
```

### Pass PulseAudio TCP to Container
```bash
sudo docker run --rm --network host \
  -e PULSE_SERVER=tcp:127.0.0.1:4713 \
  theme-song ffplay -nodisp -autoexit songs/test.mp3
```

## Docker Version Limitations (19.03)
- No BuildKit by default
- No `docker compose` (only `docker-compose` if installed separately — it's not)
- Limited multi-stage build support
- `--mount` syntax may not work; use `-v` instead
