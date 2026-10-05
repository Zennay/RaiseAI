param(
    [Parameter(Mandatory = $false)]
    [string]$Watch
)

$ErrorActionPreference = "Stop"
$Repo = "Zennay/RaiseAI"
$Workflow = "watch-app-test.yml"
$Package = "nl.zennay.raiseai"
$WorkDir = Join-Path $env:TEMP "raiseai-watch-install"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is niet gevonden in PATH."
    }
}

Require-Command "gh"
Require-Command "adb"

Write-Host "== Raise AI Watch installer =="

gh auth status --hostname github.com | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is niet ingelogd. Run eerst: gh auth login"
}

if (Test-Path $WorkDir) {
    Remove-Item $WorkDir -Recurse -Force
}
New-Item -ItemType Directory -Path $WorkDir | Out-Null

$runJson = gh run list --repo $Repo --workflow $Workflow --branch main --status success --limit 1 --json databaseId,headSha,createdAt
if ($LASTEXITCODE -ne 0) {
    throw "Kon de nieuwste succesvolle Raise AI build niet vinden."
}

$run = $runJson | ConvertFrom-Json | Select-Object -First 1
if (-not $run) {
    throw "Geen succesvolle main build gevonden."
}

Write-Host "Download build $($run.databaseId) @ $($run.headSha)"
gh run download $run.databaseId --repo $Repo --dir $WorkDir
if ($LASTEXITCODE -ne 0) {
    throw "Artifact-download mislukt."
}

$apk = Get-ChildItem $WorkDir -Recurse -File | Where-Object { $_.Name -match '^RaiseAI-v.+-debug\.apk$' } | Select-Object -First 1
if (-not $apk) {
    $apk = Get-ChildItem $WorkDir -Recurse -Filter "app-debug.apk" -File | Select-Object -First 1
}
if (-not $apk) {
    throw "Geen Raise AI APK gevonden in de build artifacts."
}

if ($Watch) {
    Write-Host "ADB connect $Watch"
    adb connect $Watch | Out-Host
}

$deviceLines = adb devices | Select-String "\tdevice$" | ForEach-Object { ($_.Line -split "\s+")[0] }

if ($Watch) {
    $serial = $Watch
} elseif ($deviceLines.Count -eq 1) {
    $serial = $deviceLines[0]
} else {
    throw "Verbind precies één Watch, of run: .\install-watch-windows.ps1 -Watch <IP:PORT>"
}

$watchFeature = adb -s $serial shell pm list features | Select-String "android.hardware.type.watch"
if (-not $watchFeature) {
    throw "ADB target $serial meldt zich niet als Wear OS watch."
}

$abi = (adb -s $serial shell getprop ro.product.cpu.abi).Trim()
Write-Host "Watch ABI: $abi"
if ($abi -ne "armeabi-v7a") {
    throw "Onverwachte Watch ABI: $abi (verwacht armeabi-v7a)."
}

Write-Host "Installeren: $($apk.FullName)"
adb -s $serial install -r $apk.FullName | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "APK-installatie mislukt."
}

adb -s $serial shell monkey -p $Package -c android.intent.category.LAUNCHER 1 | Out-Null

Write-Host ""
Write-Host "Geinstalleerde Raise AI versie:"
adb -s $serial shell dumpsys package $Package | Select-String "versionName=|versionCode=" | Select-Object -First 2 | ForEach-Object { $_.Line.Trim() }

Write-Host ""
Write-Host "Klaar. Raise AI is geinstalleerd en geopend op de Watch."
