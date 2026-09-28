# Builds MTG-Counter-Windows.zip: the app plus a bundled Python runtime, so
# whoever you send it to can unzip and double-click with nothing to install.
#
# Run it with make-bundle.bat (which handles the PowerShell execution policy),
# or from a PowerShell prompt in this folder.
#
# This is build tooling, not part of the app. Don't put it in the zip.

$ErrorActionPreference = "Stop"

# Python's "Windows embeddable package": the runtime and standard library with
# no installer, no registry entries and no PATH changes. It ships without pip,
# which is fine because server.py deliberately uses nothing outside the
# standard library. Checksum is from the release page at
# https://www.python.org/downloads/release/python-31315/
$Version  = "3.13.15"
$Sha256   = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
$Url      = "https://www.python.org/ftp/python/$Version/python-$Version-embed-amd64.zip"

# The files a player-host actually needs. PROJECT.md and the test scripts are
# maintainer material and stay out.
$AppFiles = @("index.html", "server.py", "start.bat", "README.md", "LICENSE")
# Folders copied whole. assets/ carries its own CREDITS.md, which has to travel
# with the art for the CC-BY licence.
$AppDirs  = @("assets")

$Root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Staging = Join-Path $Root "build\MTG-Counter"
$OutZip  = Join-Path $Root "MTG-Counter-Windows.zip"
$Cache   = Join-Path $Root "build\python-$Version-embed-amd64.zip"

Write-Host ""
Write-Host "Building the MTG Counter bundle" -ForegroundColor Cyan
Write-Host "-------------------------------"

foreach ($f in $AppFiles + $AppDirs) {
    if (-not (Test-Path (Join-Path $Root $f))) {
        throw "Missing $f - run this from the folder that has the app files in it."
    }
}

if (Test-Path (Join-Path $Root "build")) { Remove-Item (Join-Path $Root "build") -Recurse -Force }
New-Item -ItemType Directory -Path $Staging -Force | Out-Null

Write-Host "Downloading Python $Version embeddable runtime (about 10 MB)..."
$ProgressPreference = "SilentlyContinue"   # the progress bar makes this crawl
Invoke-WebRequest -Uri $Url -OutFile $Cache -UseBasicParsing

Write-Host "Verifying checksum..."
$actual = (Get-FileHash -Path $Cache -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $Sha256.ToLower()) {
    throw "Checksum mismatch. Expected $Sha256 but got $actual. Stopping rather than bundling a file that isn't what python.org published."
}
Write-Host "  checksum OK" -ForegroundColor Green

Write-Host "Unpacking the runtime into python\ ..."
Expand-Archive -Path $Cache -DestinationPath (Join-Path $Staging "python") -Force
if (-not (Test-Path (Join-Path $Staging "python\python.exe"))) {
    throw "python.exe is not where it was expected after unpacking."
}

Write-Host "Copying app files..."
foreach ($f in $AppFiles) { Copy-Item (Join-Path $Root $f) -Destination $Staging }
foreach ($d in $AppDirs)  { Copy-Item (Join-Path $Root $d) -Destination $Staging -Recurse }

Write-Host "Zipping..."
if (Test-Path $OutZip) { Remove-Item $OutZip -Force }
Compress-Archive -Path $Staging -DestinationPath $OutZip -CompressionLevel Optimal

$sizeMb = [math]::Round((Get-Item $OutZip).Length / 1MB, 1)
Write-Host ""
Write-Host "Done: $OutZip ($sizeMb MB)" -ForegroundColor Green
Write-Host ""
Write-Host "Before sending it out, sanity-check the bundle yourself:"
Write-Host "  1. Extract it somewhere else on this computer (not this folder)."
Write-Host "  2. Double-click start.bat in the extracted copy."
Write-Host "  3. Confirm it starts and a phone can reach the address it prints."
Write-Host ""
Write-Host "Then attach the zip to a GitHub release and send the link. It has"
Write-Host "an .exe inside, so email providers will strip it as an attachment."
Write-Host ""
