#!/bin/bash
# Manage WiFi networks on Azure Percept
# Usage:
#   sudo ./add_wifi.sh scan              — list available networks
#   sudo ./add_wifi.sh "SSID" "PASSWORD" — add WPA2 network
#   sudo ./add_wifi.sh "SSID" open       — add open (no password) network
#   sudo ./add_wifi.sh connect "SSID"    — connect to already-configured network

CONF="/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"

case "$1" in
    scan)
        echo "📡 Scanning for WiFi networks..."
        wpa_cli -i wlan0 scan > /dev/null 2>&1
        sleep 3
        echo ""
        printf "%-35s %-6s %s\n" "SSID" "SIGNAL" "SECURITY"
        printf "%-35s %-6s %s\n" "---" "------" "--------"
        wpa_cli -i wlan0 scan_results 2>/dev/null | tail -n +2 | \
            awk -F'\t' '$5 != "" { printf "%-35s %-6s %s\n", $5, $3, $4 }' | \
            sort -t' ' -k2 -n | uniq
        echo ""
        echo "To add a network: sudo $0 'SSID' 'PASSWORD'"
        echo "For open networks: sudo $0 'SSID' open"
        ;;

    connect)
        SSID="$2"
        if [ -z "$SSID" ]; then
            echo "Usage: sudo $0 connect 'SSID'"
            exit 1
        fi
        echo "Connecting to $SSID..."
        wpa_cli -i wlan0 reconfigure
        sleep 5
        IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP 'inet \K[\d.]+')
        if [ -n "$IP" ]; then
            echo "✅ Connected! IP: $IP"
        else
            echo "⚠️  Not connected yet. Check: sudo $0 scan"
        fi
        ;;

    *)
        SSID="$1"
        PASS="$2"

        if [ -z "$SSID" ]; then
            echo "Azure Percept WiFi Manager"
            echo ""
            echo "Usage:"
            echo "  sudo $0 scan              — list available networks"
            echo "  sudo $0 'SSID' 'PASSWORD' — add WPA2 network"
            echo "  sudo $0 'SSID' open       — add open network"
            echo "  sudo $0 connect 'SSID'    — reconnect"
            exit 0
        fi

        if grep -q "ssid=\"$SSID\"" "$CONF" 2>/dev/null; then
            echo "Network '$SSID' already configured. Use: sudo $0 connect '$SSID'"
            exit 0
        fi

        if [ "$PASS" = "open" ]; then
            cat >> "$CONF" << EOF

network={
        ssid="$SSID"
        key_mgmt=NONE
        priority=2
}
EOF
            echo "✅ Added open network: $SSID"
        else
            if [ -z "$PASS" ]; then
                echo "Usage: sudo $0 '$SSID' 'PASSWORD'  (or 'open' for no password)"
                exit 1
            fi
            cat >> "$CONF" << EOF

network={
        ssid="$SSID"
        psk="$PASS"
        priority=2
}
EOF
            echo "✅ Added WPA2 network: $SSID"
        fi

        echo "Connecting..."
        wpa_cli -i wlan0 reconfigure
        sleep 5
        IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP 'inet \K[\d.]+')
        if [ -n "$IP" ]; then
            echo "✅ Connected! IP: $IP"
            echo "SSH: ssh -i id_rsa tera@$IP"
        else
            echo "Network added. Will auto-connect when in range."
        fi
        ;;
esac
