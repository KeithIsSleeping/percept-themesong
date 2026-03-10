---
name: azure-percept-bluetooth-audio
description: >
  How to set up Bluetooth audio on Azure Percept DK which has no native audio stack.
  Uses a dedicated Docker container running D-Bus, bluetoothd, and PulseAudio.
  Apply when connecting Bluetooth speakers or playing audio on the Percept DK.
---

# Azure Percept DK — Bluetooth Audio via Docker

## The Problem
- Host OS (CBL-Mariner 1.0) has **no audio stack** — no ALSA, PulseAudio, or PipeWire
- Package repos are dead (EOL), cannot install audio packages on host
- Need Bluetooth speaker for audio output

## Solution: Dedicated bt-audio Container
Run a container with its own D-Bus + bluetoothd + PulseAudio stack:

### Prerequisites
1. **Stop host bluetooth** (so container can own the BT adapter):
   ```bash
   sudo systemctl stop bluetooth
   ```
2. **Put speaker in pairing mode** — the container's fresh bluetoothd needs to pair from scratch

### Start bt-audio Container
```bash
sudo docker run --rm -d --privileged --network host --name bt-audio \
  --entrypoint bash theme-song -c '
  mkdir -p /run/dbus
  dbus-daemon --system --fork
  bluetoothd --compat &
  sleep 3
  bluetoothctl power on
  bluetoothctl pairable on
  bluetoothctl scan on &
  sleep 5
  bluetoothctl pair <SPEAKER_MAC>
  sleep 3
  bluetoothctl trust <SPEAKER_MAC>
  bluetoothctl connect <SPEAKER_MAC>
  sleep 5
  adduser pulse bluetooth 2>/dev/null
  cat > /etc/pulse/system.pa << EOF
load-module module-native-protocol-tcp auth-anonymous=1 port=4713
load-module module-bluetooth-discover
load-module module-bluetooth-policy
load-module module-always-sink
load-module module-udev-detect
EOF
  pulseaudio --system --disallow-exit --exit-idle-time=-1 --daemonize
  sleep infinity'
```

### Playing Audio from Other Containers
Set `PULSE_SERVER` environment variable:
```bash
sudo docker run --rm --network host \
  -e PULSE_SERVER=tcp:127.0.0.1:4713 \
  -v /opt/theme-song/songs:/app/songs \
  theme-song ffplay -nodisp -autoexit songs/test.mp3
```

### In Python Code
```python
import os, subprocess
os.environ["PULSE_SERVER"] = "tcp:127.0.0.1:4713"
subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", song_path])
```

## Speaker Details
- **Model**: Tribit XSound Plus 2
- **MAC**: Replace `<SPEAKER_MAC>` with your speaker's MAC address
- Replace the MAC address in commands with your speaker's MAC

## Troubleshooting
- **No sound**: Check `bluetoothctl info <SPEAKER_MAC>` — should show `Connected: yes`
- **Connection refused**: Verify bt-audio container is running: `sudo docker ps`
- **Permission denied on BT adapter**: Make sure host bluetooth is stopped first
- **Speaker not found**: Ensure speaker is in pairing mode before starting container
- **After device reboot**: Must restart bt-audio container (speaker re-pairs from scratch)

## Architecture
```
┌─────────────────┐     TCP:4713      ┌──────────────┐
│  theme-song     │ ──────────────→   │  bt-audio    │
│  container      │  PulseAudio TCP   │  container   │
│  (ffplay)       │                   │  D-Bus       │
│                 │                   │  bluetoothd  │
│  PULSE_SERVER=  │                   │  PulseAudio  │
│  tcp:...:4713   │                   │  ↓ A2DP      │
└─────────────────┘                   └──────┬───────┘
                                             │ Bluetooth
                                      ┌──────┴───────┐
                                      │  BT Speaker  │
                                      └──────────────┘
```
