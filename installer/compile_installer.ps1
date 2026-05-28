param(
    [string]$IssPath = "L:\Softwares\REPORTE DOCENTE\installer\ReporteDocente.iss"
)

$ErrorActionPreference = "Stop"

function Find-ISCC {
    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $candidates += $cmd.Source
    }

    $found = $candidates | Select-Object -Unique | Where-Object { Test-Path $_ }
    if ($found.Count -gt 0) {
        return $found[0]
    }
    return $null
}

if (-not (Test-Path $IssPath)) {
    Write-Host "No se encontro el script ISS: $IssPath" -ForegroundColor Red
    exit 1
}

$iscc = Find-ISCC
if (-not $iscc) {
    Write-Host "ISCC.exe no esta instalado o no se encontro." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Instala Inno Setup 6 y vuelve a ejecutar este script." -ForegroundColor Cyan
    Write-Host "Descarga: https://jrsoftware.org/isdl.php" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Luego ejecuta:" -ForegroundColor Gray
    Write-Host "powershell -ExecutionPolicy Bypass -File `"$PSScriptRoot\compile_installer.ps1`"" -ForegroundColor Gray
    exit 2
}

Write-Host "Usando ISCC: $iscc" -ForegroundColor Green
& $iscc $IssPath

$outDir = "L:\Softwares\REPORTE DOCENTE\dist_installer"
if (Test-Path $outDir) {
    Write-Host ""
    Write-Host "Compilacion finalizada. Revisa:" -ForegroundColor Green
    Write-Host $outDir -ForegroundColor Green
}

