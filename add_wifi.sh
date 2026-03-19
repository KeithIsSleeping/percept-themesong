#!/bin/bash
# Add a WiFi network to the Azure Percept
# Usage: sudo ./add_wifi.sh "SSID" "PASSWORD"

SSID="$1"
PASS="$2"

if [ -z "$SSID" ] || [ -z "$PASS" ]; then
    echo "Usage: sudo ./add_wifi.sh 'SSID' 'PASSWORD'"
    exit 1
fi

CONF="/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"

if grep -q "ssid=\"$SSID\"" "$CONF"; then
    echo "Network '$SSID' already configured"
    exit 0
fi

cat >> "$CONF" << EOF

network={
        ssid="$SSID"
        psk="$PASS"
        priority=2
}
EOF

echo "Added WiFi network: $SSID"
echo "Reloading wpa_supplicant..."
wpa_cli -i wlan0 reconfigure
echo "Done. Device will auto-connect to '$SSID' when in range."
