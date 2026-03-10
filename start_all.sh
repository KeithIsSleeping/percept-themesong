#!/bin/bash
# start_all.sh — Full system startup: camera + bluetooth audio + theme song app
# Usage: sudo BT_MAC=AA:BB:CC:DD:EE:FF bash /opt/theme-song/start_all.sh

set -e

BT_MAC="${BT_MAC:?Usage: BT_MAC=AA:BB:CC:DD:EE:FF bash start_all.sh}"

echo "========================================="
echo " Azure Percept Theme Song System Startup"
echo "========================================="
echo " Bluetooth speaker: $BT_MAC"
echo ""

# Step 1: Start camera
echo "--- Step 1: Starting camera ---"
bash /opt/theme-song/start_camera.sh
echo ""

# Step 2: Stop host bluetooth so container can take over
echo "--- Step 2: Starting Bluetooth + theme song container ---"
systemctl stop bluetooth 2>/dev/null || true
docker stop theme-run 2>/dev/null && docker rm theme-run 2>/dev/null || true
sleep 1

docker run -d --name theme-run \
    --privileged --net=host \
    --device /dev/video0 --device /dev/video1 \
    -v /opt/theme-song:/opt/theme-song \
    -v /var/lib/bluetooth:/var/lib/bluetooth \
    -w /opt/theme-song \
    -e BT_MAC="$BT_MAC" \
    theme-song:latest bash entrypoint.sh

echo "Waiting for Bluetooth connection + app startup..."
sleep 20

echo ""
echo "========================================="
echo " System started!"
echo "========================================="
echo ""
echo "To check status:  docker ps"
echo "To see app logs:  docker logs theme-run -f"
echo "To stop:          docker stop theme-run"
