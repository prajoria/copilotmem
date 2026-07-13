# scripts/install-hooks.ps1
#
# One-shot per-clone setup: point Git at the in-repo hooks directory.
# Idempotent - safe to run repeatedly.
#
# See SESSION-START.md section 8.5 for what the hooks enforce.

$ErrorActionPreference = 'Stop'

$repoRoot = git rev-parse --show-toplevel
if (-not $repoRoot) {
    Write-Error "[install-hooks] Not inside a git repository."
    exit 1
}
Set-Location $repoRoot

$current = ''
try { $current = git config --local core.hooksPath } catch { $current = '' }

if ($current -eq '.githooks') {
    Write-Host "[install-hooks] Already configured: core.hooksPath = .githooks"
} else {
    git config --local core.hooksPath .githooks
    Write-Host "[install-hooks] Set core.hooksPath = .githooks"
}

Write-Host "[install-hooks] Done. Hooks in .githooks/ are now active for this clone."
Write-Host "[install-hooks] Note: on Windows, Git for Windows executes hook scripts via its bundled bash.exe."
