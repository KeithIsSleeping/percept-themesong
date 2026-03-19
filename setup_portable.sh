#!/bin/bash
# =============================================================
# Portable Setup Script for Azure Percept Theme Song System
# =============================================================
# Run this ON the Percept device via SSH to enable:
#   1. mDNS (.local hostname) — find device on any network
#   2. Add a new WiFi network — connect at work/elsewhere
#
# Usage:
#   # From your PC:
#   scp setup_portable.sh tera@<DEVICE_IP>:/tmp/
#   ssh tera@<DEVICE_IP> "chmod +x /tmp/setup_portable.sh && sudo /tmp/setup_portable.sh"
#
#   # To add work WiFi:
#   ssh tera@<DEVICE_IP> "sudo /tmp/setup_portable.sh --wifi 'YourSSID' 'YourPassword'"
# =============================================================

set -e

HOSTNAME_LOCAL="percept-theme"

setup_mdns() {
    echo "📡 Setting up mDNS (Avahi)..."

    if command -v avahi-daemon &>/dev/null; then
        echo "   Avahi already installed"
    else
        echo "   Installing avahi-daemon..."
        apt-get update -qq
        apt-get install -y -qq avahi-daemon avahi-utils libnss-mdns
    fi

    # Set a friendly hostname
    hostnamectl set-hostname "$HOSTNAME_LOCAL" 2>/dev/null || \
        echo "$HOSTNAME_LOCAL" > /etc/hostname

    # Ensure avahi is configured
    mkdir -p /etc/avahi
    cat > /etc/avahi/avahi-daemon.conf << 'EOF'
[server]
host-name=percept-theme
domain-name=local
use-ipv4=yes
use-ipv6=no
allow-interfaces=wlan0

[publish]
publish-addresses=yes
publish-hinfo=yes
publish-workstation=no

[reflector]

[rlimits]
EOF

    # Enable and start
    systemctl enable avahi-daemon
    systemctl restart avahi-daemon

    echo "   ✅ mDNS ready! Device reachable at: ${HOSTNAME_LOCAL}.local"
    echo "   Test with: ping ${HOSTNAME_LOCAL}.local"
    echo "   SSH with:  ssh -i id_rsa tera@${HOSTNAME_LOCAL}.local"
}

add_wifi() {
    local ssid="$1"
    local password="$2"

    if [ -z "$ssid" ]; then
        echo "❌ Usage: $0 --wifi 'SSID' 'PASSWORD'"
        exit 1
    fi

    echo "📶 Adding WiFi network: $ssid"

    # Check if connection already exists
    if nmcli connection show "$ssid" &>/dev/null; then
        echo "   Connection '$ssid' already exists, updating..."
        nmcli connection modify "$ssid" wifi-sec.psk "$password"
    else
        nmcli connection add type wifi con-name "$ssid" ssid "$ssid" \
            wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$password" \
            connection.autoconnect yes connection.autoconnect-priority 10
    fi

    echo "   ✅ WiFi '$ssid' configured (autoconnect enabled)"
    echo "   Current connections:"
    nmcli connection show | grep -E '(NAME|wifi)'
    echo ""
    echo "   The device will auto-connect to '$ssid' when in range."
    echo "   After connecting, find it at: ${HOSTNAME_LOCAL}.local"
}

autostart_theme() {
    echo "🔧 Setting up auto-start on boot..."

    cat > /etc/systemd/system/theme-song.service << 'EOF'
[Unit]
Description=Theme Song Entrance System
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
ExecStartPre=-/usr/bin/docker rm -f theme-run
ExecStartPre=-/bin/systemctl stop bluetooth
ExecStart=/usr/bin/docker run --name theme-run \
    --privileged --net=host \
    --device /dev/video0 --device /dev/video1 \
    -v /opt/theme-song:/opt/theme-song \
    -v /var/lib/bluetooth:/var/lib/bluetooth \
    -w /opt/theme-song \
    -e BT_MAC=F4:4E:FC:E3:F5:9C \
    theme-song:latest bash entrypoint.sh
ExecStop=/usr/bin/docker stop theme-run
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable theme-song.service

    echo "   ✅ Theme song system will auto-start on boot!"
    echo "   Control with: sudo systemctl start|stop|status theme-song"
}

# --- Main ---
case "${1:-}" in
    --wifi)
        add_wifi "$2" "$3"
        ;;
    --autostart)
        autostart_theme
        ;;
    --all)
        setup_mdns
        echo ""
        autostart_theme
        echo ""
        if [ -n "${2:-}" ]; then
            add_wifi "$2" "$3"
        fi
        ;;
    *)
        setup_mdns
        echo ""
        autostart_theme
        echo ""
        echo "================================================"
        echo "  To add a WiFi network, run:"
        echo "  sudo $0 --wifi 'YourSSID' 'YourPassword'"
        echo "================================================"
        ;;
esac
