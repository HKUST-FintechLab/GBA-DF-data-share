param(
  [Parameter(Mandatory=$true)][string]$Stage,
  [Parameter(Mandatory=$true)][string]$RunId,
  [Parameter(Mandatory=$true)][int]$Port,
  [int]$Rounds = 5
)

$ErrorActionPreference = "Stop"
$Repo  = "D:\agent\dean\0803\datademo"
$Base  = "C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\baseline_exp"
$State = Join-Path $Base ("state_" + $RunId)
$Logs  = Join-Path $Base ("logs_" + $RunId)

if (Test-Path $State) { Remove-Item -Recurse -Force $State }
if (Test-Path $Logs)  { Remove-Item -Recurse -Force $Logs }
New-Item -ItemType Directory -Force $State | Out-Null
New-Item -ItemType Directory -Force $Logs  | Out-Null

# fresh node keys every run
Get-ChildItem -Path $Stage -Recurse -Filter "node_key.pem" -ErrorAction SilentlyContinue | Remove-Item -Force

$env:FED_STATE_DIR = $State
$coord = Start-Process -FilePath "uv" `
  -ArgumentList @("run","python","-m","uvicorn","coordinator:app","--host","127.0.0.1","--port","$Port","--log-level","warning") `
  -WorkingDirectory $Repo -PassThru -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $Logs "coord.out") -RedirectStandardError (Join-Path $Logs "coord.err")

# wait for readiness
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/status" -TimeoutSec 3
    if ($null -ne $r) { $ready = $true; break }
  } catch { }
}
if (-not $ready) {
  Write-Output "FAIL: coordinator on port $Port never became ready for $RunId"
  try { Stop-Process -Id $coord.Id -Force } catch {}
  exit 1
}

$procs = @()
foreach ($n in 1,2,3) {
  $folder = Join-Path $Stage "node_$n"
  $p = Start-Process -FilePath "uv" `
    -ArgumentList @("run","python","node.py","--node-id","node_$n","--coord","http://127.0.0.1:$Port","--folder",$folder,"--modality","action","--rounds","$Rounds","--seed","$n") `
    -WorkingDirectory $Repo -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs "node_$n.out") -RedirectStandardError (Join-Path $Logs "node_$n.err")
  $procs += $p
}

$timedOut = $false
foreach ($p in $procs) {
  if (-not $p.WaitForExit(900000)) { $timedOut = $true }
}
$exits = ($procs | ForEach-Object { $_.ExitCode }) -join ","

try {
  $st = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/status" -TimeoutSec 10
  $st | ConvertTo-Json -Depth 12 | Out-File -Encoding utf8 (Join-Path $Base ("status_" + $RunId + ".json"))
  $ok = $true
} catch {
  Write-Output "FAIL: could not read status for $RunId : $_"
  $ok = $false
}

# kill the WHOLE tree: `uv run` spawns python which spawns the uvicorn worker.
& taskkill /PID $coord.Id /T /F 2>$null | Out-Null
Start-Sleep -Milliseconds 800
$still = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq $Port }
foreach ($c in $still) { try { Stop-Process -Id $c.OwningProcess -Force } catch {} }

# surface any node-side crash rather than silently accepting a short run
$errs = @()
foreach ($n in 1,2,3) {
  $e = Join-Path $Logs "node_$n.err"
  if ((Test-Path $e) -and ((Get-Item $e).Length -gt 0)) { $errs += "node_$n : " + ((Get-Content $e -Tail 2) -join " | ") }
}
if ($errs.Count -gt 0) { Write-Output ("NODE-STDERR $RunId :: " + ($errs -join " ;; ")) }

$aucs = ""
if ($ok) { $aucs = ($st.metrics | ForEach-Object { "{0:F4}" -f $_.auc }) -join " " }
Write-Output ("RESULT $RunId rounds=" + $(if($ok){$st.metrics.Count}else{"?"}) + " timedOut=$timedOut exits=$exits aucs=$aucs")
