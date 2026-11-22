# One-time source PMTiles transfer, same public source-release contract as Chicago.
# Requires existing GitHub CLI authentication to both repositories. Does NOT
# create or configure a personal access token or cross-repository action secret.
param(
  [string]$DestinationTag = "koronus-downloadable-v1-src"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$privateRepo = "messireLeonard/interactive-city-map"
$publicRepo = "messireLeonard/moscow_test"
$sourceTag = "koronus-downloadable-v1-private-source-20261122"
$expected = [ordered]@{
  "koronus.pmtiles" = @{
    Size = [long]1964280
    SHA = "d94f0ac84c187fc43711674a68a6bd376013e7bbc1d6086c27ecc603420a7dc7"
  }
  "koronus-resources.pmtiles" = @{
    Size = [long]119589679
    SHA = "523b9700d25097fafc68481d573a4022acf74fa9f1efb6d818041e8aaaf1c18a"
  }
  "SOURCE_PROVENANCE.json" = @{
    Size = [long]670
    SHA = "f26a5c7dfd85936d9dc2e9c2572ee829a9b723f83e30fd8e36f22c38132470cd"
  }
  "SHA256SUMS.txt" = @{
    Size = [long]266
    SHA = "494f9eb5cfaa686db75a2f61d7cf6f7cfe626b46be02d3d3469dc8d4e0841d12"
  }
}
function Invoke-Gh([string[]]$Argv) {
  & gh @Argv
  if ($LASTEXITCODE -ne 0) { throw "GitHub CLI failed: $($Argv[0..[Math]::Min($Argv.Length-1,3)] -join ' ')" }
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI 'gh' not found. Install/authenticate it before running the one-time transfer."
}
Invoke-Gh @("auth", "status", "--hostname", "github.com")
$destination = (& gh release view $DestinationTag --repo $publicRepo --json isDraft,assets | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $null -eq $destination) { throw "Expected moscow_test source draft does not exist" }
if ($destination.isDraft -ne $true -or $destination.assets.Count -ne 0) {
  throw "Refusing to overwrite a non-empty or published source release"
}
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("icm-koronus-transfer-" + [guid]::NewGuid().ToString("N"))
[void](New-Item -ItemType Directory -Path $temporary)
try {
  Write-Host "Downloading four source assets from private ICM release..."
  Invoke-Gh @("release", "download", $sourceTag, "--repo", $privateRepo, "--dir", $temporary)
  $found = @(Get-ChildItem -LiteralPath $temporary -File)
  if ($found.Count -ne 4 -or @($found | Where-Object { -not $expected.Contains($_.Name) }).Count -gt 0) {
    throw "Unexpected files in the private source-transfer release"
  }
  foreach ($name in $expected.Keys) {
    $path = Join-Path $temporary $name
    $file = Get-Item -LiteralPath $path -ErrorAction Stop
    if ($file.Length -ne $expected[$name].Size) { throw "Size mismatch: $name" }
    $digest = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne $expected[$name].SHA) { throw "SHA256 mismatch: $name" }
    Write-Host "Verified $name ($($file.Length) bytes)"
  }
  $provenance = Get-Content -LiteralPath (Join-Path $temporary "SOURCE_PROVENANCE.json") -Raw | ConvertFrom-Json
  if ($provenance.sourceTag -ne "v0.2.140-rc.1" -or
      $provenance.sourceCommit -ne "2f7413498af25161e765ec803073261b880ab229" -or
      $provenance.sourceArchiveSHA256 -ne "43e436b6325eceee2dcb75a59e9385ac0535393747f2e75382a6af19aefcf0b2") {
    throw "Source archive provenance mismatch"
  }
  $checksumLines = @(Get-Content -LiteralPath (Join-Path $temporary "SHA256SUMS.txt"))
  if ($checksumLines.Count -ne 3) { throw "Unexpected source checksum manifest" }
  Write-Host "Uploading verified PMTiles to the moscow_test source draft..."
  $uploadArgs = @("release","upload",$DestinationTag,"--repo",$publicRepo)
  foreach ($name in $expected.Keys) { $uploadArgs += (Join-Path $temporary $name) }
  Invoke-Gh $uploadArgs
  $uploaded = (& gh release view $DestinationTag --repo $publicRepo --json isDraft,assets | ConvertFrom-Json)
  if ($LASTEXITCODE -ne 0 -or $uploaded.isDraft -ne $true -or $uploaded.assets.Count -ne 4) {
    throw "Unexpected public draft asset inventory after upload"
  }
  foreach ($asset in $uploaded.assets) {
    if (-not $expected.Contains($asset.name) -or $asset.size -ne $expected[$asset.name].Size) {
      throw "Unexpected remote draft asset or size mismatch"
    }
  }
  Write-Host "Four source files are verified and present. Publishing the source release..."
  Invoke-Gh @("release", "edit", $DestinationTag, "--repo", $publicRepo, "--draft=false", "--prerelease")
  Write-Host "Source release published. Splitter is prepared; an explicit publish(koronus): commit starts the immutable chunk publication."
} finally {
  Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
