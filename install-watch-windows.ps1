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

function Get-SingleApkCandidate([string]$Root) {
    $versioned = @(
        Get-ChildItem $Root -Recurse -File |
            Where-Object { $_.Name -match '^RaiseAI-v.+-debug\.apk$' }
    )
    if ($versioned.Count -gt 1) {
        throw "Meerdere Raise AI APK-kandidaten gevonden in de build artifacts; installatie wordt geweigerd."
    }
    if ($versioned.Count -eq 1) {
        return $versioned[0]
    }

    $fallback = @(Get-ChildItem $Root -Recurse -Filter "app-debug.apk" -File)
    if ($fallback.Count -gt 1) {
        throw "Meerdere app-debug.apk-kandidaten gevonden in de build artifacts; installatie wordt geweigerd."
    }
    if ($fallback.Count -eq 1) {
        return $fallback[0]
    }

    throw "Geen Raise AI APK gevonden in de build artifacts."
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

$mainSha = (gh api "repos/$Repo/commits/main" --jq ".sha").Trim()
if ($LASTEXITCODE -ne 0 -or -not $mainSha) {
    throw "Kon de huidige main commit niet bepalen."
}
if ($run.headSha -ne $mainSha) {
    throw "De nieuwste main commit is nog niet succesvol gebouwd. Probeer opnieuw zodra Raise Watch app CI groen is."
}

Write-Host "Download build $($run.databaseId) @ $($run.headSha)"
gh run download $run.databaseId --repo $Repo --dir $WorkDir
if ($LASTEXITCODE -ne 0) {
    throw "Artifact-download mislukt."
}

$apk = Get-SingleApkCandidate $WorkDir

if ($Watch) {
    Write-Host "ADB connect $Watch"
    adb connect $Watch | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "ADB connect naar $Watch is mislukt."
    }
}

$deviceOutput = @(adb devices)
if ($LASTEXITCODE -ne 0) {
    throw "Kon de ADB device-lijst niet lezen."
}
$deviceLines = @(
    $deviceOutput |
        Select-String "\tdevice$" |
        ForEach-Object { ($_.Line -split "\s+")[0] }
)

if ($Watch) {
    if ($deviceLines -notcontains $Watch) {
        throw "Het expliciete Watch-target $Watch staat niet als verbonden device in adb devices."
    }
    $serial = $Watch
} elseif ($deviceLines.Count -eq 1) {
    $serial = $deviceLines[0]
} else {
    throw "Verbind precies één Watch, of run: .\install-watch-windows.ps1 -Watch <IP:PORT>"
}

$watchFeature = adb -s $serial shell pm list features | Select-String "android.hardware.type.watch"
if ($LASTEXITCODE -ne 0 -or -not $watchFeature) {
    throw "ADB target $serial meldt zich niet als verbonden Wear OS watch."
}

$abi = (adb -s $serial shell getprop ro.product.cpu.abi).Trim()
if ($LASTEXITCODE -ne 0 -or -not $abi) {
    throw "Kon de ABI van ADB target $serial niet bepalen."
}
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
if ($LASTEXITCODE -ne 0) {
    throw "Raise AI kon na installatie niet worden gestart."
}

Write-Host ""
Write-Host "Geinstalleerde Raise AI versie:"
adb -s $serial shell dumpsys package $Package | Select-String "versionName=|versionCode=" | Select-Object -First 2 | ForEach-Object { $_.Line.Trim() }
if ($LASTEXITCODE -ne 0) {
    throw "Kon de geinstalleerde Raise AI pakketstatus niet uitlezen."
}

Write-Host ""
Write-Host "Klaar. Raise AI is geinstalleerd en geopend op de Watch."
