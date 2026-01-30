# ================================
# VERIFY_STATIC.ps1
# ================================

Write-Host "Running static verification..." -ForegroundColor Green

python -m compileall -q src
if ($LASTEXITCODE -ne 0) { throw "Compile failed" }

pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

Write-Host "Static verification PASSED." -ForegroundColor Green
