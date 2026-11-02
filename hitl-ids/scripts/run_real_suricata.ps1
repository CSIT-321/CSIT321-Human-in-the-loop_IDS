<# Execute the actual detector offline. Never captures/replays traffic on a network.
   Prepare the official engine, config and general-purpose rules as documented in
   docs/real-suricata-pcap-validation.md. Use a new output directory for each run. #>
param(
    [Parameter(Mandatory=$true)][string]$Suricata,
    [Parameter(Mandatory=$true)][string]$Configuration,
    [Parameter(Mandatory=$true)][string]$Rules,
    [Parameter(Mandatory=$true)][string]$Pcap,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$enginePath = (Resolve-Path -LiteralPath $Suricata).Path
$configPath = (Resolve-Path -LiteralPath $Configuration).Path
$rulesPath = (Resolve-Path -LiteralPath $Rules).Path
$pcapPath = (Resolve-Path -LiteralPath $Pcap).Path
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Refusing to append to an existing detector output directory' }
$outputPath = (New-Item -ItemType Directory -Path $OutputDirectory).FullName
$testPath = (New-Item -ItemType Directory -Path (Join-Path $outputPath 'config-test')).FullName
$started = [DateTime]::UtcNow.ToString('o')
& $enginePath --build-info *> (Join-Path $outputPath 'build-info.txt')
if ($LASTEXITCODE -ne 0) { throw "Suricata build-info failed: $LASTEXITCODE" }
$testArgs = @('-T', '-c', $configPath, '-S', $rulesPath, '-l', $testPath)
& $enginePath @testArgs *> (Join-Path $outputPath 'config-test.log')
if ($LASTEXITCODE -ne 0) { throw "Suricata configuration test failed: $LASTEXITCODE" }
$runArgs = @('-c', $configPath, '-S', $rulesPath, '-r', $pcapPath, '-l', $outputPath, '--runmode', 'single')
& $enginePath @runArgs *> (Join-Path $outputPath 'run.log')
if ($LASTEXITCODE -ne 0) { throw "Suricata offline processing failed: $LASTEXITCODE" }
$evePath = Join-Path $outputPath 'eve.json'
if (!(Test-Path -LiteralPath $evePath)) { throw 'Actual detector did not produce eve.json' }
$types = @{}
Get-Content -LiteralPath $evePath | ForEach-Object {
    if ($_.Trim()) { $eventType = ($_ | ConvertFrom-Json).event_type; $types[$eventType] = 1 + $types[$eventType] }
}
$audit = [ordered]@{
    engine = $enginePath; startedAtUtc = $started; finishedAtUtc = [DateTime]::UtcNow.ToString('o')
    configurationTestArguments = $testArgs; offlineArguments = $runArgs
    configurationTestExit = 0; offlineExit = 0
    pcap = $pcapPath; pcapBytes = (Get-Item -LiteralPath $pcapPath).Length
    pcapSha256 = (Get-FileHash -LiteralPath $pcapPath -Algorithm SHA256).Hash.ToLowerInvariant()
    configSha256 = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash.ToLowerInvariant()
    rulesSha256 = (Get-FileHash -LiteralPath $rulesPath -Algorithm SHA256).Hash.ToLowerInvariant()
    eveSha256 = (Get-FileHash -LiteralPath $evePath -Algorithm SHA256).Hash.ToLowerInvariant()
    eventTypes = $types; mode = 'offline PCAP read only'
}
$audit | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputPath 'run-evidence.json') -Encoding utf8
$audit | ConvertTo-Json -Depth 5
