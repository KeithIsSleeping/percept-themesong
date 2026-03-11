#!/bin/bash

BT_MAC="${BT_MAC:?Set BT_MAC to your Bluetooth speaker MAC address (e.g. AA:BB:CC:DD:EE:FF)}"
echo "🎵 Theme Song Entrance System"
echo "   Bluetooth speaker: $BT_MAC"

# --- D-Bus ---
mkdir -p /run/dbus
rm -f /run/dbus/pid
dbus-daemon --system --nofork &
sleep 2

# --- Bring up BT adapter before starting BlueZ ---
hciconfig hci0 up 2>/dev/null || true
sleep 1

# --- BlueZ ---
bluetoothd &
sleep 2

# --- Add pulse user to bluetooth group ---
groupadd bluetooth 2>/dev/null || true
usermod -a -G bluetooth pulse 2>/dev/null || true

# --- D-Bus policy for PulseAudio -> BlueZ ---
cat > /etc/dbus-1/system.d/pulse-bt.conf << 'POLICYEOF'
<!DOCTYPE busconfig PUBLIC
 "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <policy user="pulse">
    <allow send_destination="org.bluez"/>
  </policy>
  <policy context="default">
    <allow send_destination="org.bluez"/>
  </policy>
</busconfig>
POLICYEOF

# --- Power on ---
printf 'power on\nquit\n' | bluetoothctl
sleep 1

# --- PulseAudio (system mode, BT + TCP, low-latency) ---
mkdir -p /var/run/pulse /var/lib/pulse /etc/pulse
rm -f /var/run/pulse/pid
cat > /etc/pulse/daemon.conf << 'DAEMONEOF'
default-fragments = 2
default-fragment-size-msec = 5
high-priority = yes
realtime-scheduling = yes
DAEMONEOF
pulseaudio --system --disallow-exit --no-cpu-limit \
  --load="module-bluetooth-discover" \
  --load="module-bluetooth-policy" \
  --load="module-native-protocol-tcp auth-anonymous=1 port=4713" \
  --log-level=error &
sleep 3

# --- Connect speaker ---
echo "Connecting to $BT_MAC..."
bluetoothctl connect "$BT_MAC" &
BT_PID=$!
sleep 12
wait $BT_PID 2>/dev/null

if printf "info $BT_MAC\nquit\n" | bluetoothctl 2>&1 | grep -q "Connected: yes"; then
    echo "✅ Bluetooth speaker connected!"
    sleep 2
    SINK=$(PULSE_SERVER=tcp:127.0.0.1:4713 pactl list sinks short 2>/dev/null | grep bluez | head -1)
    if [ -n "$SINK" ]; then
        echo "✅ Audio sink: $SINK"
    else
        echo "⚠️  BT connected but no audio sink yet (will auto-discover)"
    fi
else
    echo "⚠️  Speaker not connected (is it turned on?)"
    echo "   System will run; audio plays when speaker connects."
fi

export PULSE_SERVER="tcp:127.0.0.1:4713"
echo ""

exec python3 src/main.py "$@"
