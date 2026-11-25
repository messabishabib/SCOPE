$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$docsDirectory = Join-Path $repositoryRoot "docs"
$sourceName = "energy-storage-model-and-roadmap.md"
$htmlPath = Join-Path $docsDirectory "_build\energy-storage-model-and-roadmap.html"
$pdfPath = Join-Path $docsDirectory "energy-storage-model-and-roadmap.pdf"

$quartoCommand = Get-Command quarto -ErrorAction SilentlyContinue
$quartoPath = if ($quartoCommand) {
    $quartoCommand.Source
} elseif (Test-Path -LiteralPath "C:\Program Files\Quarto\bin\quarto.exe") {
    "C:\Program Files\Quarto\bin\quarto.exe"
} else {
    throw "Quarto is required. Install it from https://quarto.org/docs/get-started/."
}

$browserCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$browserPath = $browserCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $browserPath) {
    throw "Google Chrome or Microsoft Edge is required to print the rendered article to PDF."
}

Push-Location $docsDirectory
try {
    & $quartoPath render $sourceName
    if ($LASTEXITCODE -ne 0) {
        throw "Quarto rendering failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $htmlPath)) {
    throw "Quarto completed without creating the expected HTML file: $htmlPath"
}

$htmlUri = [System.Uri]::new($htmlPath).AbsoluteUri
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$browserProfile = Join-Path $temporaryRoot ("scope-pdf-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $browserProfile | Out-Null
$browserArguments = @(
    "--headless=new",
    "--disable-gpu",
    "--user-data-dir=$browserProfile",
    "--allow-file-access-from-files",
    "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=5000",
    "--no-pdf-header-footer",
    "--print-to-pdf=$pdfPath",
    $htmlUri
)

try {
    & $browserPath $browserArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Browser PDF generation failed with exit code $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath $pdfPath) -or (Get-Item -LiteralPath $pdfPath).Length -eq 0) {
        throw "The browser did not create a valid PDF file: $pdfPath"
    }
} finally {
    $resolvedProfile = [System.IO.Path]::GetFullPath($browserProfile)
    if ($resolvedProfile.StartsWith($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedProfile)) {
        Remove-Item -LiteralPath $resolvedProfile -Recurse -Force
    }
}

$sizeKiB = [Math]::Round((Get-Item -LiteralPath $pdfPath).Length / 1KB, 1)
Write-Host "Created $pdfPath ($sizeKiB KiB)"
