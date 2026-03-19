# Find the Azure Percept device on your local network
# Scans the local subnet for SSH on port 22, then checks hostname
param(
    [string]$Subnet = ""
)

if (-not $Subnet) {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback" -and $_.PrefixOrigin -eq "Dhcp" } | Select-Object -First 1).IPAddress
    if ($ip) {
        $Subnet = ($ip -replace '\.\d+$', '')
    } else {
        Write-Host "Could not detect subnet. Usage: .\find_percept.ps1 -Subnet 192.168.1"
        exit 1
    }
}

Write-Host "Scanning $Subnet.0/24 for Azure Percept..." -ForegroundColor Cyan

$found = $false
1..254 | ForEach-Object -Parallel {
    $ip = "$using:Subnet.$_"
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $tcp.BeginConnect($ip, 22, $null, $null)
        $success = $result.AsyncWaitHandle.WaitOne(200)
        if ($success -and $tcp.Connected) {
            Write-Output $ip
        }
    } catch {} finally {
        $tcp.Close()
    }
} -ThrottleLimit 50 | ForEach-Object {
    $ip = $_
    Write-Host "  Found SSH at $ip - checking hostname..." -ForegroundColor Yellow
    try {
        $key = "$PSScriptRoot\id_rsa"
        $result = ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=3 -o BatchMode=yes "tera@$ip" "hostname" 2>$null
        if ($result -match "percept") {
            Write-Host ""
            Write-Host "  FOUND Azure Percept at $ip (hostname: $result)" -ForegroundColor Green
            Write-Host "  SSH:  ssh -i id_rsa tera@$ip" -ForegroundColor Green
            Write-Host ""
            $found = $true
        }
    } catch {}
}

if (-not $found) {
    Write-Host ""
    Write-Host "  Device not found on $Subnet.0/24" -ForegroundColor Red
    Write-Host "  - Is it powered on and connected to this WiFi?" -ForegroundColor Red
    Write-Host "  - Try connecting to its AP: apd-d8c0a6594e8d" -ForegroundColor Red
}
