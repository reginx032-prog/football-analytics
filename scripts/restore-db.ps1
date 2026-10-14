[CmdletBinding()]
param(
    [string]$DumpPath = (Join-Path $PSScriptRoot '..\football_data.dump'),
    [string]$Container = 'football_db_container',
    [string]$Database = 'football_data',
    [string]$User = 'admin',
    [switch]$SkipBackup,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is not available in PATH.'
}

$resolvedDump = Resolve-Path -LiteralPath $DumpPath -ErrorAction Stop
$isRunning = docker inspect -f '{{.State.Running}}' $Container 2>$null
if ($LASTEXITCODE -ne 0 -or $isRunning -ne 'true') {
    throw "PostgreSQL container '$Container' is not running."
}

if (-not $SkipBackup) {
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backupName = "football_data_before_restore_$timestamp.dump"
    $backupPath = Join-Path (Split-Path $resolvedDump.Path -Parent) $backupName

    Write-Host "Creating local backup: $backupPath"
    docker exec $Container pg_dump -U $User -d $Database -Fc -f "/tmp/$backupName"
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to create the pre-restore database backup.'
    }
    docker cp "${Container}:/tmp/$backupName" $backupPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to copy the pre-restore database backup locally.'
    }
}

if (-not $Force) {
    $confirmation = Read-Host "Restore '$($resolvedDump.Path)' into '$Database'? Existing tables will be replaced. Type YES to continue"
    if ($confirmation -ne 'YES') {
        Write-Host 'Restore cancelled.'
        exit 0
    }
}

$containerDump = '/tmp/football_data_restore.dump'
docker cp $resolvedDump.Path "${Container}:$containerDump"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to copy the restore dump to the PostgreSQL container.'
}

docker exec $Container pg_restore -U $User -d $Database --clean --if-exists --no-owner $containerDump
if ($LASTEXITCODE -ne 0) {
    throw 'Database restore failed.'
}

Write-Host "Database '$Database' restored successfully from '$($resolvedDump.Path)'."
