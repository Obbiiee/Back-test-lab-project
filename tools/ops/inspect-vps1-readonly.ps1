<#
Read-only VPS1 inspection. Run from the Windows account that owns the SSH key.
This script never accepts a new host key and never sends private-key contents.
#>
[CmdletBinding()]
param(
    [string]$HostName = '172.255.209.213',
    [string]$UserName = 'developer',
    [string]$KeyPath = (Join-Path $env:USERPROFILE '.ssh\riksora_vps1')
)

$ErrorActionPreference = 'Stop'
$ssh = Get-Command ssh.exe -ErrorAction Stop
$keygen = Get-Command ssh-keygen.exe -ErrorAction Stop
$knownHosts = Join-Path $env:USERPROFILE '.ssh\known_hosts'

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "SSH identity file is unavailable: $KeyPath"
}
if (-not (Test-Path -LiteralPath $knownHosts -PathType Leaf)) {
    throw "No trusted known_hosts file exists at $knownHosts. Verify the VPS fingerprint through a trusted channel first."
}

$trustedEntry = & $keygen.Source -F $HostName -f $knownHosts 2>$null
if ($LASTEXITCODE -ne 0 -or -not $trustedEntry) {
    throw "No trusted host-key entry exists for $HostName. No connection was attempted. Verify the fingerprint through a trusted channel first."
}

$remote = @'
set -eu
printf '%s\n' '=== IDENTITY ==='
hostnamectl --static 2>/dev/null || hostname
cat /etc/machine-id
. /etc/os-release
printf '%s %s\n' "$ID" "$VERSION_ID"
printf '%s\n' '=== CPU ==='
nproc
lscpu | awk -F: '/^(Model name|CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\))/ {gsub(/^ +/,"",$2); print $1 ": " $2}'
printf '%s\n' '=== MEMORY ==='
grep -E 'MemTotal|MemAvailable|SwapTotal|SwapFree' /proc/meminfo
printf '%s\n' '=== DISK ==='
df -h / /home
printf '%s\n' '=== PRESSURE ==='
for resource in cpu memory io; do
  if test -r "/proc/pressure/$resource"; then cat "/proc/pressure/$resource"; fi
done
printf '%s\n' '=== RUNNING SERVICES ==='
systemctl --no-pager --type=service --state=running 2>/dev/null | head -60 || true
printf '%s\n' '=== RELEVANT PROCESS NAMES ==='
ps -eo pid,ppid,comm,pcpu,rss --sort=-pcpu | awk 'NR==1 || /caddy|uvicorn|app_api|worker|postgres|riksora/ {print; n++; if (n>=40) exit}'
printf '%s\n' '=== PROJECT SERVICE CONFIG (ALLOWLISTED VALUES) ==='
for f in "$HOME/prod/app.env" "$HOME/.config/riksora/app.env"; do
  if test -r "$f"; then
    echo "config_file_present=$f"
    sed -nE '/^(BTL_WORKERS|BTL_API_ADMISSION_LIMIT|BTL_DB_BUDGET|BTL_DIRECT_OPERATION_CONCURRENCY|BTL_RESEARCH_QUEUE_LIMIT|BTL_RESEARCH_USER_QUEUE_LIMIT|BTL_RESEARCH_QUEUE_TTL_S|BTL_RESEARCH_JOB_DEADLINE_S|BTL_TICK_CHECKPOINT_FORMAT)=/p' "$f"
  fi
done
'@

$arguments = @(
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-o', 'IdentitiesOnly=yes',
    '-o', 'ConnectTimeout=10',
    '-i', $KeyPath,
    "$UserName@$HostName",
    $remote
)

& $ssh.Source @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Read-only VPS1 inspection failed with ssh exit code $LASTEXITCODE."
}
