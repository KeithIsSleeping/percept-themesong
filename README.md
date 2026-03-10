# 🎵 Theme Song Entrance System

A face-recognition doorbell that plays personalized theme songs when people walk into a room. Built on the [Azure Percept DK](https://learn.microsoft.com/en-us/azure/azure-percept/) — runs 100% locally with no cloud services.

**How it works:** A USB webcam watches the doorway. When it detects a face, it matches it against enrolled people using OpenVINO AI models. If it recognizes you, it plays your theme song over a Bluetooth speaker.

> **⚠️ Disclaimer:** This is an unofficial hobby project. It is not affiliated with, endorsed by, or supported by Microsoft. Azure Percept was retired in March 2023 — there is no official support, no cloud services, and no warranty. Use at your own risk.

> 📖 **[Read the full build journey →](JOURNEY.md)** — Every dead end, hardware failure, and hard-won lesson from taking a factory-new Percept DK to a working system.

---

## Hardware You'll Need

| Component | Notes |
|---|---|
| Azure Percept DK | NXP i.MX8M carrier board (ARM Cortex-A53, 4GB RAM) |
| USB webcam | Any UVC-compatible camera (e.g., Logitech C920/C922). Plugs into the carrier board USB-A port. |
| Bluetooth speaker | Any A2DP-compatible speaker. Tested with Tribit XSound Plus 2. |
| USB-C power supply | Included with the DK |

> **Why USB webcam?** The Vision SoM's built-in MIPI camera has a known manufacturing defect where the ribbon cable comes loose, producing permanent black frames. A USB webcam is more reliable and easier to set up.

---

## Quick Start

```bash
# 1. SSH into the device
ssh <YOUR_USER>@<DEVICE_IP>

# 2. Clone/copy this repo to the device
cd /opt/theme-song

# 3. Build the Docker image (downloads AI models automatically)
sudo docker build -t theme-song:latest .

# 4. Add your songs to songs/
#    (MP3 or WAV files)

# 5. Pair your Bluetooth speaker (one-time setup, see below)

# 6. Start everything
sudo BT_MAC=AA:BB:CC:DD:EE:FF bash start_all.sh

# 7. Enroll faces (see Enrollment section below)
```

---

## Setup Guide

### 1. Flash the No-Auth Firmware

The factory firmware requires Microsoft's dead attestation servers. You **must** apply the final community firmware update:

1. Download the [Attestation Removal Tool](https://download.microsoft.com/download/7/7/a/77a2f57a-0ede-48be-988c-11796f7948da/Azure%20Percept%20DK%20SoM%20Attestation%20Update%20Tool.zip)
2. Transfer to device: `scp input/* <YOUR_USER>@<DEVICE_IP>:/tmp/fw_update/`
3. Run on device:
   ```bash
   cd /tmp/fw_update
   sudo chmod +x AP_Peripheral_Installer_v0.1
   sudo ./AP_Peripheral_Installer_v0.1
   ```
4. Verify: `lsusb -d 045e:066f -v` — should show `bcdDevice 3.00`

### 2. Build the Docker Image

```bash
cd /opt/theme-song
sudo docker build -t theme-song:latest .
```

This installs all dependencies and downloads the OpenVINO face detection/recognition models at build time.

### 3. Pair Your Bluetooth Speaker

First-time pairing must be done interactively inside the container:

```bash
# Stop host bluetooth so the container can control the adapter
sudo systemctl stop bluetooth

# Start a temporary container with BT access
sudo docker run --rm -it --privileged --net=host \
    -v /var/lib/bluetooth:/var/lib/bluetooth \
    theme-song:latest bash

# Inside the container:
mkdir -p /run/dbus && dbus-daemon --system --nofork &
sleep 2 && hciconfig hci0 up && bluetoothd &
sleep 2

# Pair the speaker (put it in pairing mode first!)
bluetoothctl
# > power on
# > scan on
# (wait for your speaker's MAC to appear)
# > trust AA:BB:CC:DD:EE:FF
# > pair AA:BB:CC:DD:EE:FF
# > quit
exit
```

After pairing, the keys are saved to `/var/lib/bluetooth/` and future connections happen automatically.

### 4. Add Songs

Copy MP3 or WAV files to the `songs/` directory on the device:

```bash
scp mysong.mp3 <YOUR_USER>@<DEVICE_IP>:/opt/theme-song/songs/
```

### 5. Start the System

```bash
sudo BT_MAC=AA:BB:CC:DD:EE:FF bash /opt/theme-song/start_all.sh
```

Or run the container directly:

```bash
sudo systemctl stop bluetooth
sudo docker run -d --name theme-run \
    --privileged --net=host \
    --device /dev/video0 --device /dev/video1 \
    -v /opt/theme-song:/opt/theme-song \
    -v /var/lib/bluetooth:/var/lib/bluetooth \
    -w /opt/theme-song \
    -e BT_MAC=AA:BB:CC:DD:EE:FF \
    theme-song:latest bash entrypoint.sh
```

---

## Enrolling Faces

### From Webcam (Interactive)

Stand in front of the camera and slowly turn your head for varied angles:

```bash
sudo docker exec -it theme-run \
    python3 src/enroll.py --name alice --song songs/mysong.mp3 --captures 15
```

### From Photos

Provide a folder of photos (different angles/lighting work best):

```bash
# Put photos in photos/alice/
sudo docker exec theme-run \
    python3 src/enroll_photo.py --name alice --song songs/mysong.mp3 --photos photos/alice/
```

### Combined (Recommended)

For best recognition accuracy, enroll from both photos AND webcam captures. The photo enrollment creates the initial embedding file, and webcam enrollment adds to it — giving the model varied training data.

```bash
# Step 1: Enroll from photos
python3 src/enroll_photo.py --name alice --song songs/mysong.mp3 --photos photos/alice/

# Step 2: Add webcam captures (merges with existing embeddings)
python3 src/enroll.py --name alice --song songs/mysong.mp3 --captures 15
```

### Enrollment Tips

- **More is better** — 15-25 total embeddings gives reliable recognition
- **Vary angles** — face the camera, then slowly turn left/right during webcam capture
- **Vary lighting** — if possible, enroll in similar lighting to where the camera is placed
- **Photo diversity** — use photos from different years, lighting, and angles
- **Test after enrolling** — check logs (`docker logs theme-run -f`) to see similarity scores

---

## Configuration

Edit `config.yaml` to tune behavior:

```yaml
# --- Key Settings ---
recognition:
  threshold: 0.35         # Similarity threshold (0.3-0.5 typical)
                          # Lower = more strict, Higher = more lenient

playback:
  cooldown_seconds: 300   # Seconds before replaying someone's song
  max_duration: 30        # Limit song playback to N seconds (null = full song)
  volume: 0.8             # 0.0 to 1.0
  stranger_song: null     # Path to song for unrecognized faces (null = disabled)
  bt_keepalive_interval: 300  # Silent ping interval to prevent BT speaker sleep

general:
  log_level: "INFO"       # Set to DEBUG for troubleshooting
  detection_interval: 0.5 # Seconds between detection cycles
```

### Recognition Threshold Tuning

| Threshold | Behavior |
|---|---|
| 0.25 | Very strict — may miss people at bad angles |
| 0.35 | **Recommended** — good balance of accuracy and tolerance |
| 0.45 | Lenient — may occasionally match wrong people |
| 0.50+ | Too loose for most setups |

Check similarity scores in the logs to tune:
```bash
docker logs theme-run -f
# Look for: 👋 Welcome alice! (confidence: 0.99, similarity: 0.623)
```

---

## Architecture

```
┌──────────────────────────────────────┐
│          Docker Container            │
│  ┌─────────────────────────────┐     │
│  │  D-Bus → BlueZ → PulseAudio│     │ Bluetooth audio stack
│  │  (A2DP sink over TCP:4713)  │     │
│  └─────────────────────────────┘     │
│  ┌─────────────────────────────┐     │
│  │  main.py                    │     │ Detection loop
│  │  ├─ camera.py    (webcam)   │     │   USB webcam → frames
│  │  ├─ face_detector.py        │     │   OpenVINO face detection
│  │  ├─ face_recognizer.py      │     │   OpenVINO face re-id + matching
│  │  └─ song_player.py          │     │   ffplay → PulseAudio → BT speaker
│  └─────────────────────────────┘     │
└──────────────────────────────────────┘
     │              │            │
  /dev/video0   /var/lib/bt   /opt/theme-song
  (USB webcam)  (BT pairing)  (songs, data, config)
```

### AI Models (OpenVINO)

| Model | Purpose | Size |
|---|---|---|
| `face-detection-retail-0005` | Detect faces in frames | ~2MB (FP16) |
| `face-reidentification-retail-0095` | Generate 256-d face embeddings | ~4MB (FP16) |

Both models run on CPU. Downloaded automatically during `docker build`.

---

## Project Structure

```
├── README.md               ← You are here
├── config.yaml             ← All tunable settings
├── Dockerfile              ← Docker image build
├── entrypoint.sh           ← Container startup (BT + audio + app)
├── requirements.txt        ← Python dependencies
├── setup_models.sh         ← Downloads OpenVINO models
├── start_all.sh            ← One-command full system start
├── start_camera.sh         ← Camera detection (USB or Vision SoM)
├── src/
│   ├── main.py             ← Main detection loop
│   ├── camera.py           ← Camera abstraction (USB/RTSP/static)
│   ├── face_detector.py    ← Face detection wrapper
│   ├── face_recognizer.py  ← Face recognition + embedding matching
│   ├── song_player.py      ← Audio playback with cooldowns + BT keep-alive
│   ├── enroll.py           ← Webcam-based face enrollment
│   └── enroll_photo.py     ← Photo-based face enrollment
├── songs/                  ← Your MP3/WAV theme songs (not tracked)
├── photos/                 ← Your enrollment photos (not tracked)
├── data/faces/             ← Generated face embeddings (not tracked)
├── models/                 ← AI models (auto-downloaded at build)
└── .github/skills/         ← Device troubleshooting guides
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| No faces detected | Check webcam: `ls /dev/video*`. Ensure it's plugged into the USB-A port. |
| Low similarity scores | Re-enroll with more photos + webcam captures. Use varied angles/lighting. |
| No audio from speaker | Is speaker on and paired? Check: `docker logs theme-run` for BT connection status. |
| Speaker goes to sleep | `bt_keepalive_interval` in config sends periodic silence to keep it awake. |
| Songs overlap | Shouldn't happen — the player blocks concurrent playback. Restart container if stuck. |
| "authentication status: 0" loop | Wrong eyemodule image. Use `azureeyemodule:2301-1-noauth`. |
| Black camera frames | Vision SoM MIPI cable issue — use a USB webcam instead. |
| VPU stuck at `03e7:f63b` | Full reboot needed: `sudo reboot` |
| Container can't find BT adapter | Make sure `sudo systemctl stop bluetooth` ran before starting container. |

### Useful Commands

```bash
# View live logs
docker logs theme-run -f

# Check if BT speaker is connected
docker exec theme-run bluetoothctl info $BT_MAC

# Restart after config changes
docker restart theme-run

# Stop the system
docker stop theme-run

# Re-pair Bluetooth speaker
docker exec -it theme-run bluetoothctl
```

---

## How It Works

1. **Camera loop** runs at ~2 FPS, grabbing frames from the USB webcam
2. **Face detection** (`face-detection-retail-0005`) finds faces in each frame
3. **Face recognition** (`face-reidentification-retail-0095`) generates a 256-dimensional embedding for each detected face
4. **Matching** compares the embedding against all enrolled faces using cosine similarity
5. **Song playback** triggers via ffplay → PulseAudio → Bluetooth A2DP when a match exceeds the threshold
6. **Cooldown** prevents the same person's song from replaying within the configured window
7. **Adaptive polling** — when faces are visible, detection speeds up to ~20 FPS for instant response; when idle, drops to 2 FPS to save CPU
8. **Stranger detection** (optional) — plays a designated song after 5 consecutive unrecognized face detections

---

## Known Limitations

- **Azure Percept is retired hardware** — no new firmware updates, no cloud services
- **Vision SoM camera unreliable** — MIPI ribbon cable defect is common; USB webcam recommended
- **CPU-only inference** — the Myriad X VPU could accelerate models but requires the eyemodule container; CPU inference on the i.MX8M works but adds ~200-400ms latency per frame
- **Single-speaker only** — Bluetooth A2DP supports one audio sink at a time

## License

MIT
