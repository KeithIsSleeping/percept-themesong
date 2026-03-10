---
name: azure-percept-camera-fix
description: Fix Azure Percept DK Vision SoM camera producing black/blank frames after Microsoft retirement (March 2023). Covers firmware update, noauth container, USB permissions, and MIPI cable reseat.
tags:
  - azure-percept
  - camera
  - troubleshooting
  - firmware
  - vision-som
---

# SKILL.md — Azure Percept DK Camera Fix (Post-Retirement)

## Problem
After Microsoft retired Azure Percept DK (March 2023), the Vision SoM camera produces
black/blank frames. The RTSP stream runs but shows no video content.

## Root Causes

### 1. Authentication Loop (Software)
The original `azureeyemodule:preload-devkit` container tries to authenticate with
`auth.projectsantacruz.azure.net:443` which is now dead. This causes an infinite
"authentication status: 0" loop and the camera never initializes.

### 2. MIPI Ribbon Cable (Hardware)
Even with correct software, the internal MIPI ribbon cable connecting the camera sensor
to the SoM board can be loose — especially in factory-new or shipped devices.

## Solution

### Step 1: Apply Attestation Removal Firmware
Download from Microsoft:
```
https://download.microsoft.com/download/7/7/a/77a2f57a-0ede-48be-988c-11796f7948da/Azure%20Percept%20DK%20SoM%20Attestation%20Update%20Tool.zip
```

```bash
sudo chmod +x AP_Peripheral_Installer_v0.1
sudo ./AP_Peripheral_Installer_v0.1
```

Verify: `lsusb -d 045e:066f -v` should show `bcdDevice 3.00`

### Step 2: Use the noauth Container
Stop the old container and pull the new one:
```bash
sudo docker stop azureeyemodule 2>/dev/null
sudo docker pull mcr.microsoft.com/azureedgedevices/azureeyemodule:2301-1-noauth
```

### Step 3: Fix USB Permissions
The noauth container runs as `apdk_app` (not root). The VPU USB device needs
world-writable permissions:
```bash
# Find the VPU device number
lsusb | grep 03e7
# e.g., Bus 001 Device 003 → /dev/bus/usb/001/003
sudo chmod 666 /dev/bus/usb/001/003
```

### Step 4: Start the Container
```bash
sudo docker run --rm -d --privileged --network host \
  --name eyemodule \
  mcr.microsoft.com/azureedgedevices/azureeyemodule:2301-1-noauth
```

Expected logs:
- `libusb_open_device_with_vid_pid VID 0x3e7 PID 0x2485 found`
- `Skipping authentication.`
- `Raw RTSP stream enabled`

### Step 5: Reseat MIPI Cable (if still black frames)
If logs look clean but frames are still black:
1. Power off the device completely
2. Unscrew 4 screws on Vision SoM cover (hex tool included in box)
3. Locate the MIPI ribbon cable under the heatsink
4. Flip up the small plastic latch, remove cable, reinsert straight, press latch down
5. Reassemble, power on, repeat Steps 3-4

## Key Technical Details
- VPU USB IDs: `03e7:2485` (booted) → `03e7:f63b` (running firmware)
- SoM Controller: `045e:066f` (Azure Eye SoM Controller)
- VPU only boots to 2485 on fresh power cycle; drops to f63b permanently after firmware load
- Camera is MIPI internally — NOT a /dev/video device, NOT UVC
- RTSP streams: `rtsp://device-ip:8554/raw`, `rtsp://device-ip:8554/result`
- IoT Edge errors (IOTEDGE_AUTHSCHEME) are cosmetic and can be ignored
- GStreamer plugin warnings are cosmetic (optional codecs)

## References
- [Blog: Applying Final Firmware Update](https://thisismydemo.cloud/post/applying-the-final-firmware-update-for-the-azure-percept-dk/)
- [Microsoft: Troubleshooting Blank Frames](https://techcommunity.microsoft.com/blog/iotblog/troubleshooting-blank-frames-on-azure-percept-device-kit/2642760)
- [ASUS: Unsupported SoM Fix PDF](https://dlcdnets.asus.com/pub/ASUS/mb/Embedded_IPC/DKSC-101/Unsupported_SoM_Fix_for_Azure_Percept_DK.pdf)
- Audio noauth container: `mcr.microsoft.com/azureedgedevices/azureearspeechclientmodule:1.0.4-noauth`
