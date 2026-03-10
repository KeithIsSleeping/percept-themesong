# Building on a Dead Platform: Azure Percept DK in 2026

A detailed account of taking a factory-new Azure Percept DK — a product Microsoft retired in March 2023 — and building a working face-recognition theme song system from scratch. Every dead end, hardware failure, and hard-won fix documented.

---

## The Starting Point

The Azure Percept DK is an edge AI development kit built around an NXP i.MX8M carrier board (ARM Cortex-A53, 4GB RAM) with an Intel Movidius Myriad X Vision SoM for accelerated computer vision. Microsoft designed it to work with Azure IoT and cloud AI services — services that were permanently shut down in March 2023.

What we wanted to build: a system that recognizes faces via camera and plays personalized theme songs through a Bluetooth speaker when people enter a room. No cloud, no internet, fully local.

What follows is every lesson learned along the way.

---

## Phase 1: Getting Into the Device

### The OS: CBL-Mariner Linux 1.0

The Percept runs Microsoft's CBL-Mariner Linux (now called Azure Linux). It's a minimal, container-optimized distro. Key facts:

- **SSH user**: the account you create during OOBE setup, with key-based auth and sudo access
- **Docker 19.03** pre-installed — this is your entire development environment
- **Python 3.7 is stripped** — missing the `xml` module, so you can't even bootstrap pip
- **Package repos are dead** — CBL-Mariner 1.0 is EOL, `tdnf install` fails for everything
- **No audio stack** — no ALSA, PulseAudio, or PipeWire, and you can't install them

**Lesson learned**: The host OS is essentially read-only. Everything runs in Docker containers. Don't fight this — embrace it.

### WiFi Persistence Bug

After initial setup, we discovered WiFi didn't survive reboots. Every power cycle required re-running the OOBE (out-of-box experience) setup to reconnect.

**Root cause**: `oobe.service` was enabled and ran on every boot, taking over WiFi. Meanwhile, `wpa_supplicant.service` was disabled.

**Fix**:
```bash
sudo systemctl enable wpa_supplicant.service
sudo systemctl disable oobe.service
```

The WiFi config was already saved in `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` — it just wasn't being loaded on boot. After this fix, the device auto-connects to WiFi within ~30 seconds of power-on.

**Lesson learned**: The OOBE service is designed for first-time setup. Disable it once you're past initial config, or it will interfere on every boot.

### DHCP and IP Addresses

The device gets a DHCP address that can change between reboots. We saw it alternate between .212 and .213 on the same network. If you're SSHing in frequently, either set a static lease on your router or use mDNS.

---

## Phase 2: The Vision SoM Camera — A Long Dead End

This was by far the most time-consuming part of the project, spanning multiple sessions and dozens of hours. The end result: the camera was physically defective from the factory.

### The Two-Part Post-Retirement Fix

The Vision SoM requires two fixes to work without Microsoft's cloud:

1. **Firmware update**: Apply `AP_Peripheral_Installer_v0.1` to update the SoM controller from bcdDevice 1.00 to 3.00. This removes the attestation requirement. Download: [Microsoft's Attestation Removal Tool](https://download.microsoft.com/download/7/7/a/77a2f57a-0ede-48be-988c-11796f7948da/Azure%20Percept%20DK%20SoM%20Attestation%20Update%20Tool.zip)

2. **Container update**: Replace the old `azureeyemodule:preload-devkit` (2021) with `azureeyemodule:2301-1-noauth` (January 2023). The old container loops forever trying to authenticate with dead Microsoft servers.

**Critical USB permission gotcha**: The noauth container runs as user `apdk_app`, not root. You must `chmod 666` the VPU's USB device file before starting:
```bash
VPU_BUS=$(lsusb | grep "03e7:2485" | awk '{print $2}')
VPU_DEV=$(lsusb | grep "03e7:2485" | awk '{print $4}' | tr -d ':')
chmod 666 "/dev/bus/usb/${VPU_BUS}/${VPU_DEV}"
```

### VPU USB States

The Intel Myriad X VPU cycles through two USB states:

| USB ID | State | Meaning |
|---|---|---|
| `03e7:2485` | Boot mode | Ready for firmware upload. Only appears on fresh power cycle. |
| `03e7:f63b` | Loopback/Running | Firmware loaded. Permanent until next reboot. |

**Critical**: Once any process claims the VPU (eyemodule, `_azureeye`, anything), it transitions from `2485` → `f63b` and **never comes back** without a full power cycle. USB resets, unbind/rebind — nothing works. You get one shot per boot.

### What We Tried

| Approach | Result |
|---|---|
| Old eyemodule container | "authentication status: 0" loop forever |
| `azure-percept` Python library | `authorize()` tries to reach dead `auth.projectsantacruz.azure.net:443` |
| `_azureeye.prepare_eye()` with VPU firmware | Blocks indefinitely on `f63b` device |
| `_azureeye.get_frame()` while eyemodule running | XLink assertion failure (conflict) |
| Direct firmware upload via pyusb | USB write call blocks/hangs |
| New noauth container | VPU boots perfectly, RTSP streams active, but **all frames black** |
| Two different VPU firmwares (Jan 2021 vs Dec 2021) | Both produce identical black frames |
| Three different resolutions (native, 720p, 1080p) | All black |
| Both MIPI connectors on the SoM board | Both black |
| Multiple ribbon cable reseats | No change |

Every single frame from the MIPI camera had `mean=16.0, std=0.0` — exactly the YUV "no signal" black level (0x10). The VPU was booting, firmware was loading, RTSP was streaming, models were running — but the camera sensor itself was producing nothing.

**Conclusion**: Manufacturing defect. The MIPI camera sensor in this factory-new unit was dead on arrival. We confirmed this by running a USB webcam on the same device simultaneously — the webcam produced perfect frames while the MIPI camera continued outputting black.

**Lesson learned**: If your Vision SoM camera produces solid black frames after applying both firmware and container fixes, and reseating the ribbon cable doesn't help — it's likely a hardware defect. Don't spend days debugging software. Plug in a USB webcam.

---

## Phase 3: USB Webcam — The Pivot

After confirming the Vision SoM camera was dead, we plugged a Logitech C922 Pro Stream Webcam into the carrier board's USB-A port. It appeared immediately as `/dev/video0` and `/dev/video1`.

The camera.py abstraction was designed to try USB webcam first, then fall back to RTSP, then to a static test image:

```python
# Priority: USB webcam → RTSP (Vision SoM) → static image
video_devices = sorted(glob.glob("/dev/video*"))
for dev in video_devices:
    cap = cv2.VideoCapture(idx)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            return cap  # Use this camera
```

**Lesson learned**: Design your camera abstraction to gracefully fall through multiple sources. The Vision SoM camera wasn't worth the engineering effort when a $30 USB webcam works perfectly.

---

## Phase 4: Face Detection — Silent Failures

With the webcam working, we moved to face enrollment and detection. This uncovered two critical bugs in how OpenVINO models handle data.

### Bug 1: uint8 vs float32 Input

OpenVINO's `face-detection-retail-0005` model expects `float32` input tensors with shape `[1, 3, 300, 300]`. When you preprocess a frame with OpenCV:

```python
resized = cv2.resize(frame, (300, 300))  # Returns uint8!
blob = resized.transpose(2, 0, 1).reshape(1, 3, 300, 300)
# blob is uint8 — model will silently produce garbage
```

The model doesn't throw an error. It accepts the `uint8` tensor and returns results — they're just all wrong (zero detections or garbage confidence values).

**Fix**: Always cast to `float32`:
```python
blob = resized.transpose(2, 0, 1).reshape(1, 3, 300, 300).astype(np.float32)
```

This same issue affected both the face detection and face re-identification models.

### Bug 2: NumPy Array View Iteration

The detection model outputs shape `[1, 1, N, 7]`. A natural way to iterate:

```python
for d in results[0][0]:
    confidence = float(d[2])
    x1 = int(d[3] * width)  # Can produce values like -4,942,324,039,680
```

The problem: `results[0][0]` creates a numpy array view, and doing `int(d[3] * width)` on a view sometimes produces astronomically wrong values. This was intermittent and extremely confusing to debug.

**Fix**: Use explicit indexing with `float()` conversion:
```python
for i in range(results.shape[2]):
    confidence = float(results[0, 0, i, 2])
    x1 = int(float(results[0, 0, i, 3]) * width)  # Always correct
```

**Lesson learned**: OpenVINO (and most ML frameworks) fail silently on dtype mismatches. If your model returns zero detections or garbage values, check your input dtype first. And never iterate over numpy array views when extracting scalar values — use explicit indexing.

---

## Phase 5: Bluetooth Audio — Running a Full Stack in Docker

The host OS has no audio support at all. No ALSA, no PulseAudio, no PipeWire, and the package repos are dead so you can't install them. The solution: run an entire Bluetooth audio stack inside a Docker container.

### The Architecture

```
Docker Container (--privileged --net=host)
├── D-Bus daemon (system bus)
├── bluetoothd (BlueZ daemon)
├── PulseAudio (system mode)
│   ├── module-bluetooth-discover
│   ├── module-bluetooth-policy
│   └── module-native-protocol-tcp (port 4713)
└── Application (ffplay → PulseAudio → BT speaker)
```

### Key Steps

1. **Stop host bluetooth** — The container needs exclusive access to the Bluetooth adapter:
   ```bash
   sudo systemctl stop bluetooth
   ```

2. **Mount Bluetooth pairing keys** — So the container can reconnect to previously paired devices:
   ```bash
   -v /var/lib/bluetooth:/var/lib/bluetooth
   ```

3. **D-Bus policy file** — PulseAudio needs permission to talk to BlueZ over D-Bus:
   ```xml
   <busconfig>
     <policy user="pulse">
       <allow send_destination="org.bluez"/>
     </policy>
   </busconfig>
   ```

4. **Start services in order**: D-Bus → hciconfig up → bluetoothd → PulseAudio → bluetoothctl connect

5. **First-time pairing** must be done interactively:
   ```
   bluetoothctl
   > scan on
   > trust AA:BB:CC:DD:EE:FF
   > pair AA:BB:CC:DD:EE:FF
   > connect AA:BB:CC:DD:EE:FF
   ```

### Bluetooth Speaker Sleep

Most Bluetooth speakers auto-sleep after 10-15 minutes of silence. We solved this with a keep-alive thread that sends 1 second of silence through ffplay every 5 minutes:

```python
ffplay -f lavfi -i anullsrc=r=44100:cl=mono -t 1 -nodisp -autoexit -loglevel quiet
```

**Lesson learned**: Running PulseAudio + BlueZ in a Docker container is entirely possible but requires `--privileged` and `--net=host`. The startup order matters, and you need a D-Bus policy file for PulseAudio to discover Bluetooth devices.

---

## Phase 6: Face Recognition Tuning

### Enrollment Quality Matters Enormously

Our first enrollment used only webcam captures — 20 frames from a single angle and lighting condition. Recognition scores were terrible: 0.2-0.3 similarity even for the enrolled person.

The breakthrough was **combined enrollment** — photos from multiple years/angles/lighting conditions, plus webcam captures from the actual deployment position:

| Enrollment Method | Similarity Scores |
|---|---|
| Webcam only (20 frames, one angle) | 0.2 - 0.3 |
| Photos only (8 varied photos) | 0.3 - 0.5 |
| Photos + webcam (23 total) | 0.4 - 0.76 |

**Lesson learned**: Use 15-25 embeddings from diverse sources. The photos teach the model your face across variations; the webcam captures teach it the specific camera position and lighting.

### Threshold Tuning

The cosine similarity threshold determines who gets recognized:

| Threshold | Trade-off |
|---|---|
| 0.25 | Very strict — misses enrolled people at bad angles |
| 0.35 | Good balance — recognizes most angles, few false positives |
| 0.45 | Lenient — may match wrong people |

We settled on **0.35** with a **5-frame stranger streak** requirement before triggering any action on unknown faces. This prevents single bad frames (person turning, partial occlusion) from triggering false "stranger" detections.

### Adaptive Detection Speed

The detection loop uses adaptive timing:
- **No faces visible**: 500ms between frames (2 FPS, saves CPU)
- **Faces detected**: 50ms between frames (~20 FPS, stays responsive)
- **Song just triggered**: 0ms delay (instant response)

This gives near-instant recognition when someone walks in while keeping CPU usage low during idle periods.

---

## Phase 7: Song Playback

Audio plays through ffplay (from FFmpeg) to PulseAudio's TCP socket:

```bash
PULSE_SERVER=tcp:127.0.0.1:4713 ffplay -nodisp -autoexit -volume 80 -t 30 song.mp3
```

Key features:
- **Per-person cooldown** (configurable, default 5 minutes) — prevents the same song from looping when someone stays in frame
- **Max duration** (configurable, default 30 seconds) — clips songs via ffplay's `-t` flag
- **Concurrent playback prevention** — tracks the ffplay subprocess and blocks new plays while one is active
- **BT keep-alive** — background thread sends silence to prevent speaker auto-sleep

---

## Docker Development Tips for Azure Percept

### Windows → Linux File Transfer Pain

If you develop on Windows and deploy to the Percept:

1. **Line endings**: Every script will have `\r` that breaks bash. Fix with:
   ```bash
   sed -i 's/\r//' script.sh
   ```

2. **Nested quoting is impossible**: PowerShell → SSH → Docker → bash → Python with f-strings and quotes will break in creative ways. **Always write code to a .py file, SCP it to the device, and run it there.**

3. **Build times**: Docker builds on the ARM Cortex-A53 are slow (10-15 minutes for a full build). Cache your layers wisely.

### Docker 19.03 Limitations

- No BuildKit by default
- No `docker compose` (only the separate `docker-compose` binary, which isn't installed)
- Limited multi-stage build support
- Use `-v` volume mounts instead of `--mount` syntax
- SSL certificates can be flaky — use `curl -sk` for downloads in containers

---

## What Worked, What Didn't

### ✅ What Worked
- Docker containers as the entire development environment
- USB webcam as a reliable camera source
- OpenVINO face models on CPU (fast enough for real-time on ARM)
- PulseAudio + BlueZ in Docker for Bluetooth audio
- Photo + webcam combined enrollment for robust recognition
- Adaptive detection loop for responsiveness + efficiency

### ❌ What Didn't Work
- Vision SoM's MIPI camera (manufacturing defect, wasted days debugging)
- `azure-percept` Python library (depends on dead cloud servers)
- Old `azureeyemodule:preload-devkit` container (authentication loop)
- Host OS for anything application-level (no pip, no audio, dead repos)
- Inline Python/bash commands over SSH from PowerShell (quoting hell)
- Webcam-only enrollment (insufficient angle/lighting diversity)
- Low similarity thresholds without streak counters (false stranger detections)

### 🤔 Lessons for Anyone Finding a Percept DK in 2024+

1. **Apply the two-part fix immediately**: Firmware 3.0 + noauth container. Don't waste time with the old software.
2. **Buy a USB webcam**: The Vision SoM camera may or may not work, and debugging it is a nightmare. A $30 webcam is a guaranteed working camera.
3. **Everything runs in Docker**: Accept this early. The host OS is a thin Docker host and nothing more.
4. **OpenVINO runs well on CPU**: The Myriad X VPU could theoretically accelerate inference, but CPU inference on the i.MX8M is fast enough for most projects (~200-400ms per frame for face detection + recognition).
5. **Budget time for Bluetooth**: Getting BT audio working in a container is a multi-hour adventure the first time.
6. **The device is still useful**: Despite being retired, the hardware is a capable edge AI platform. The NXP i.MX8M + 4GB RAM + Docker + USB ports make it a legitimate SBC for local ML projects.

---

## Final System Architecture

```
┌─────────────────────────────────────────────┐
│              Docker Container               │
│  ┌───────────────────────────────────────┐  │
│  │  Bluetooth Audio Stack                │  │
│  │  D-Bus → BlueZ → PulseAudio (TCP)    │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │  Theme Song Application               │  │
│  │  USB Webcam → Face Detection          │  │
│  │  (OpenVINO) → Face Recognition        │  │
│  │  → Song Player (ffplay → PulseAudio)  │  │
│  └───────────────────────────────────────┘  │
└──────────────┬──────────┬──────────┬────────┘
          /dev/video0  /var/lib/bt  /opt/theme-song
          (webcam)     (BT keys)    (songs, data, config)
                                         │
                                    ┌────┴────┐
                                    │ Speaker │ (Bluetooth A2DP)
                                    └─────────┘
```

Total time from unboxing to working system: ~20 hours across multiple sessions. Most of that was the Vision SoM camera dead end. With this guide, you could do it in 2-3 hours.
