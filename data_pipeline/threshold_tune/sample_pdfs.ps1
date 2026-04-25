$outputRoot = "C:\Users\$env:USERNAME\.ipython\ask-maroon\data_pipeline\threshold_tune\pdfs"
$checkpointFile = "C:\Users\$env:USERNAME\.ipython\ask-maroon\data_pipeline\threshold_tune\checkpoint.txt"

Set-Location "C:\Users\$env:USERNAME\Downloads\rclone-v1.73.5-windows-amd64\rclone-v1.73.5-windows-amd64"
Get-Random -SetSeed 42

$files = rclone lsf r2:ask-maroon-dev/archive/pdfs --recursive --files-only |
    Where-Object { $_ -match "\.pdf$" -and $_ -notmatch "ipynb_checkpoints" }

$byYear = $files | Group-Object { ($_ -split "/")[0] }

# set num for stratified sample by year
$sampled = foreach ($group in $byYear) {
    $group.Group | Get-Random -Count ([Math]::Min(5, $group.Count))
}

if (Test-Path $checkpointFile) {
    $completed = Get-Content $checkpointFile
    $sampled = $sampled | Where-Object { $completed -notcontains $_ }
    Write-Host "Resuming: $($completed.Count) files already done, $($sampled.Count) remaining"
}

$tempFile = New-TemporaryFile
$sampled | Set-Content $tempFile

# bump or revert num transfers depending on connection speed
rclone copy r2:ask-maroon-dev/archive/pdfs $outputRoot --files-from $tempFile --progress --transfers 4 --checksum

$sampled | Add-Content $checkpointFile
Remove-Item $tempFile