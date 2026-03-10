#!/bin/bash
# start_camera.sh — Start the camera (Vision SoM or USB webcam)
# Usage: sudo bash /opt/theme-song/start_camera.sh

set -e

echo "=== Azure Percept Camera Startup ==="

# Check for USB webcam first
USB_CAM=$(ls /dev/video* 2>/dev/null | head -1)
if [ -n "$USB_CAM" ]; then
    echo "✅ USB webcam detected at $USB_CAM"
    echo "The theme-song app will use it directly (no eyemodule needed)"
    exit 0
fi

echo "No USB webcam found. Trying Vision SoM camera..."

# Check VPU state
VPU=$(lsusb | grep 03e7 || true)
if echo "$VPU" | grep -q "2485"; then
    echo "✅ VPU in booted state (03e7:2485)"
elif echo "$VPU" | grep -q "f63b"; then
    echo "⚠️  VPU in loopback state (03e7:f63b) — need a full reboot first!"
    echo "Run: sudo reboot"
    exit 1
else
    echo "⚠️  VPU not found! Check Vision SoM USB-C connection."
    echo "Or plug in a USB webcam to the carrier board's USB-A port."
    exit 1
fi

# Stop any existing eyemodule
docker stop eyemodule 2>/dev/null && echo "Stopped old eyemodule" || true
docker rm eyemodule 2>/dev/null || true
sleep 1

# Fix USB permissions for apdk_app user
VPU_BUS=$(lsusb | grep "03e7:2485" | awk '{print $2}')
VPU_DEV=$(lsusb | grep "03e7:2485" | awk '{print $4}' | tr -d ':')
USB_PATH="/dev/bus/usb/${VPU_BUS}/${VPU_DEV}"
echo "Setting permissions on $USB_PATH"
chmod 666 "$USB_PATH"

# Start the noauth eyemodule
echo "Starting azureeyemodule:2301-1-noauth..."
docker run --rm -d --privileged --network host \
    --name eyemodule \
    mcr.microsoft.com/azureedgedevices/azureeyemodule:2301-1-noauth \
    /app/inference \
        --model=/app/data/ssd_mobilenet_v2_coco.blob \
        --label=/app/data/labels.txt \
        --mvcmd=/eyesom/mx.mvcmd \
        --parser=ssd100

echo "Waiting 20s for VPU boot..."
sleep 20

# Check logs
echo ""
echo "=== Container logs ==="
docker logs eyemodule 2>&1 | grep -v 'gst-plugin-scanner'

# Quick frame test
echo ""
echo "=== Testing camera frame ==="
docker run --rm --network host -v /opt/theme-song/data:/data theme-song:latest python3 -c "
import cv2, sys
cap = cv2.VideoCapture('rtsp://localhost:8554/raw', cv2.CAP_FFMPEG)
if not cap.isOpened():
    print('❌ Cannot connect to RTSP stream')
    sys.exit(1)
for i in range(10):
    ret, frame = cap.read()
    if ret:
        m = frame.mean()
        if m > 20:
            cv2.imwrite('/data/live_frame.jpg', frame)
            print(f'✅ CAMERA WORKING! Frame {i}: mean={m:.1f}')
            cap.release()
            sys.exit(0)
cap.release()
print(f'❌ Vision SoM camera producing black frames.')
print('Options:')
print('  1. Plug a USB webcam into the carrier board USB-A port')
print('  2. Open the Vision SoM and reseat the MIPI ribbon cable')
print('  3. See .github/skills/azure-percept-camera-fix.md')
sys.exit(1)
"
