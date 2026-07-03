<#
.SYNOPSIS
  Layered Terraform apply/destroy runner that ENFORCES dependency order.
  (Korean rationale + full docs: infra/README.md. This script is intentionally
   ASCII-only so Windows PowerShell 5.1 cannot mis-decode it as cp949 --
   a UTF-8-without-BOM .ps1 with non-ASCII comments corrupts adjacent code lines.)

.DESCRIPTION
  Layers are dependency-ordered:
    shared (foundation) -> karpenter (cluster runtime)
      -> target | backend | console (read shared) -> monitoring (reads shared+backend+console)
  Each lower layer reads the layer(s) above via terraform_remote_state outputs.

  Order matters (real 2026-07-03 incident):
    - destroy: tearing down shared before target breaks target's remote_state.shared read.
    - destroy: karpenter must go before shared, else EKS/VPC destroy stalls on orphan nodes.
  This runner walks layers forward for apply and reverse for destroy, stopping
  immediately if any layer fails (so a broken layer does not cascade).

.PARAMETER Action   apply | destroy | plan | validate
.PARAMETER Layer    one layer name, or 'all' (default).
.PARAMETER AutoApprove   skip approval prompt on apply/destroy (-auto-approve).
.PARAMETER AwsProfile    AWS_PROFILE to use; empty = ambient credentials.
.PARAMETER ExtraArgs     extra args appended to each terraform call, e.g.
                         -ExtraArgs '-var','enable_custom_domain=true' (use with -Layer console).

.EXAMPLE
  ./infra/deploy.ps1 -Action apply
.EXAMPLE
  ./infra/deploy.ps1 -Action destroy -AutoApprove
.EXAMPLE
  ./infra/deploy.ps1 -Action apply -Layer console -ExtraArgs '-var','enable_custom_domain=true'
.EXAMPLE
  ./infra/deploy.ps1 -Action validate
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('apply', 'destroy', 'plan', 'validate')][string]$Action,
  [ValidateSet('all', 'shared', 'karpenter', 'target', 'backend', 'console', 'monitoring')][string]$Layer = 'all',
  [switch]$AutoApprove,
  [string]$AwsProfile = '',
  [string[]]$ExtraArgs = @()
)

# Do NOT use 'Stop' here: PowerShell 5.1 turns terraform's stderr (progress lines)
# into a terminating error under 'Stop', corrupting exit-code checks. Control flow
# below relies on explicit throw + $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'

# Dependency order (SSOT). apply = forward, destroy = reverse.
#   karpenter right after shared (needs the live cluster).
#   monitoring last (reads backend + console outputs).
$ApplyOrder = @('shared', 'karpenter', 'target', 'backend', 'console', 'monitoring')

$InfraRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($AwsProfile -ne '') {
  $env:AWS_PROFILE = $AwsProfile
  Write-Host "AWS_PROFILE = $AwsProfile" -ForegroundColor DarkGray
}

if ($Layer -eq 'all') {
  $layers = if ($Action -eq 'destroy') { $ApplyOrder[($ApplyOrder.Count - 1)..0] } else { $ApplyOrder }
}
else {
  $layers = @($Layer)
}

Write-Host ""
Write-Host "== terraform $Action | order: $($layers -join ' -> ') ==" -ForegroundColor Cyan
if ($Action -eq 'destroy' -and $Layer -eq 'all') {
  Write-Host "   (destroy is reverse: monitoring first, shared last)" -ForegroundColor Yellow
}
Write-Host ""

function Invoke-Layer {
  param([string]$L, [string]$Act)

  $dir = Join-Path $InfraRoot $L
  if (-not (Test-Path (Join-Path $dir 'main.tf'))) {
    throw "layer '$L' has no main.tf at: $dir"
  }

  Write-Host "--- [$L] terraform $Act ---" -ForegroundColor Green

  # Push-Location moves the real CWD (a cmdlet handles non-ASCII paths fine),
  # so terraform runs with no '-chdir=<abs path>' arg (that arg mangles under cp949).
  Push-Location $dir
  try {
    if ($Act -eq 'validate') {
      # syntax only, no billing / no backend access
      & terraform init -backend=false -input=false
      if ($LASTEXITCODE -ne 0) { throw "[$L] init failed" }
      & terraform validate
      if ($LASTEXITCODE -ne 0) { throw "[$L] validate failed" }
      return
    }

    # plan / apply / destroy need a real backend init.
    # -reconfigure: a prior 'validate' run leaves .terraform with backend=false;
    # without it, switching back to the S3 backend would prompt (and -input=false would fail).
    # No local state ever exists here, so there is nothing to migrate -- safe.
    & terraform init -reconfigure -input=false
    if ($LASTEXITCODE -ne 0) { throw "[$L] init failed" }

    $tfArgs = @($Act, '-input=false') + $ExtraArgs
    if ($Act -in @('apply', 'destroy') -and $AutoApprove) { $tfArgs += '-auto-approve' }

    & terraform @tfArgs
    if ($LASTEXITCODE -ne 0) { throw "[$L] $Act failed -- stopping (state protection)" }
  }
  finally {
    Pop-Location
  }
}

foreach ($l in $layers) {
  Invoke-Layer -L $l -Act $Action
  Write-Host ""
}

Write-Host "== done: terraform $Action ($($layers -join ', ')) ==" -ForegroundColor Cyan
if ($Action -eq 'apply') {
  Write-Host "Cost discipline: after verifying, run './infra/deploy.ps1 -Action destroy -AutoApprove'." -ForegroundColor Yellow
}
