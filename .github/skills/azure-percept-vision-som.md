---
name: azure-percept-vision-som
description: >
  Technical details about the Azure Percept Vision SoM (Intel Myriad X VPU),
  its USB states, boot sequence, attestation requirements, and camera access methods.
  Apply when working with the Vision SoM camera, face detection, or VPU inference.
---

# Azure Percept Vision SoM — Camera & VPU

## USB Device States
The Vision SoM presents different USB IDs depending on its state:

| VID:PID       | Description                          | Meaning                    |
|---------------|--------------------------------------|----------------------------|
| `045e:066d`   | 4-Port USB 3.1 Hub                   | Always present             |
| `045e:066e`   | 2-Port USB 2.1 Hub                   | Always present             |
| `045e:066f`   | Azure Eye SoM Controller             | **VPU UNBOOTED**           |
| `03e7:f63b`   | Intel VSC Loopback Device            | Intermediate/waiting state |
| `03e7:2485`   | Intel Myriad X VPU                   | **VPU BOOTED — ready**     |

## Boot Sequence
1. `authorize()` → contacts Azure attestation server → authenticates SoM
2. VPU transitions: `045e:066f` → `03e7:f63b` → `03e7:2485`
3. `prepare_eye(mx.mvcmd)` → uploads VPU firmware blob to booted Myriad X
4. `start_inference(blob_path, ["/camera1"])` → starts camera + inference pipeline

## Post-Retirement Problem (March 2023)
- Azure attestation server is **permanently offline**
- `authorize()` fails with "Error connect to server"
- VPU cannot transition to `03e7:2485` after cold boot
- Firmware re-flash returns ERROR 0X87F2 (already at 3.0.0.0)
- The preloaded `azureeyemodule` container also fails ("authentication status: 0" loop)
- `prepare_eye()` hangs when VPU is in unbooted/loopback state

## _azureeye Python C Extension
- Package: `azure-percept` on PyPI (v0.0.13, by christian-vorhemus)
- Source: github.com/christian-vorhemus/azure-percept-py
- **Requires**: `numpy<2` (conflicts with latest opencv-python-headless)
- Location of VPU firmware: `/usr/local/lib/python3.9/site-packages/azure/iot/percept/assets/mx.mvcmd`

### API Reference
```python
_azureeye.authorize()                              # Talks to (dead) attestation server
_azureeye.prepare_eye(mvcmd_path)                  # Upload firmware to booted VPU
_azureeye.start_inference(blob_path, input_list)   # Start inference (blob_path=.blob model, input_list=["/camera1"])
_azureeye.get_frame()                              # Returns frame in CHW format
_azureeye.get_inference(ret_img, input, h, w)      # Get inference results
_azureeye.start_recording(filepath)                # Start MP4 recording
_azureeye.stop_recording()                         # Stop recording
_azureeye.stop_inference()                         # Stop inference
_azureeye.close_eye()                              # Cleanup
```

### Frame Format
`get_frame()` returns CHW (channels, height, width). Convert to OpenCV BGR:
```python
im = _azureeye.get_frame()
im = np.moveaxis(im, 0, -1)        # CHW → HWC
im = np.ascontiguousarray(im, dtype=np.uint8)
```

## Camera Access Alternatives
Since the VPU can't boot after cold boot:

1. **USB webcam** (recommended fallback): Plug any USB webcam into the carrier board USB-A port.
   Access via OpenCV: `cv2.VideoCapture(0)` or `cv2.VideoCapture("/dev/video0")`.
2. **RTSP** (only if azureeyemodule works): `rtsp://127.0.0.1:8554/raw` (816×616 frames).
3. **Network camera**: Use any IP camera's RTSP stream via OpenCV.

## RTSP Details (When Working)
- Raw stream: `rtsp://127.0.0.1:8554/raw` — unprocessed camera frames
- Result stream: `rtsp://127.0.0.1:8554/result` — with inference overlay
- Frame size: 816×616
- Access via OpenCV: `cv2.VideoCapture("rtsp://127.0.0.1:8554/raw")`
