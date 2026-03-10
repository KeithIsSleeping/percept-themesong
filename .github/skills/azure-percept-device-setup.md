---
name: azure-percept-device-setup
description: >
  How to SSH into and work with an Azure Percept DK running CBL-Mariner Linux 1.0.
  Covers device access, Docker usage, filesystem layout, and host OS limitations.
  Apply when working with Azure Percept DK, CBL-Mariner, or NXP i.MX8M ARM64 boards.
---

# Azure Percept DK — Device Setup & Access

## Hardware
- **SoC**: NXP i.MX8M Quad (ARM Cortex-A53, 4 cores, 2.7 GB RAM, aarch64)
- **Storage**: 2 GB root (`/`) + 10.5 GB `/var` (Docker images live here)
- **Vision SoM**: Intel Movidius Myriad X VPU via USB-C (MIPI camera, not exposed as `/dev/video`)

## OS & Access
- **OS**: CBL-Mariner Linux 1.0, kernel 5.4.3
- **SSH**: user you created during OOBE setup (has sudo). Uses key-based auth.
- **IP**: DHCP-assigned; can change on reboot. Check router or use `10.1.1.1` if connected via AP.

## Host Limitations (Critical)
- **Python 3.7 is stripped**: missing `xml` module, no pip, cannot bootstrap pip.
- **Package repos are dead**: CBL-Mariner 1.0 is EOL, `tdnf install` fails for most packages.
- **No audio stack**: no ALSA, PulseAudio, or PipeWire; repos too old to install them.
- **Consequence**: ALL application code must run inside Docker containers.

## Docker (19.03)
- Pre-installed and working. IoT Edge 1.1.0 installed but unused.
- Images stored on `/var` (10.5 GB available).
- Use `python:3.9-slim-bullseye` as base image — works well on aarch64.
- **Windows line endings**: Scripts transferred from Windows have `\r`. Always run:
  ```bash
  sed -i "s/\r//" script.sh
  ```
- **Nested quoting**: PowerShell → SSH → Docker → bash is painful. Upload script files via SCP instead of inline commands.
- **SSL certs**: `wget` may fail; use `curl -sk` for downloads inside containers.
- **overlay2 corruption**: If Docker breaks, remove `/var/lib/docker/overlay2` + `/image` + `/containers`, restart Docker.

## Filesystem Layout
```
/opt/theme-song/          # Project root on device
├── src/                  # Python source
├── models/               # OpenVINO IR models
├── songs/                # MP3 theme songs
├── data/faces/           # Enrolled face embeddings
└── fw_update/            # Firmware tools (persistent)
```

## Key Commands
```bash
# SSH in
ssh <YOUR_USER>@<DEVICE_IP>

# Copy files to device
scp localfile.py <YOUR_USER>@<DEVICE_IP>:/opt/theme-song/src/

# Run a command in Docker
sudo docker run --rm --privileged -v /opt/theme-song:/app theme-song python3 src/script.py

# Check disk space
df -h /var
```
