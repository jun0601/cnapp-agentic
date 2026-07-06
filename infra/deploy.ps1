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

  # backend ships REAL lambda code: bundle dirs + psycopg2 layer must exist before
  # plan/apply (archive_file zips them). validate skips data sources, so no build needed there.
  if ($L -eq 'backend' -and $Act -in @('plan', 'apply')) {
    Write-Host "--- [backend] packaging lambda bundles (build_lambdas.py) ---" -ForegroundColor Green
    & python (Join-Path $dir 'build_lambdas.py')
    if ($LASTEXITCODE -ne 0) { throw "[backend] lambda build failed -- not deploying stale/missing bundles" }
  }

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

    # Fail fast instead of hanging: apply/destroy without -auto-approve shows an
    # interactive 'yes?' prompt. In a non-interactive session (redirected stdin --
    # CI, a backgrounded runner, an agent tool) terraform never receives the answer
    # and blocks FOREVER on that prompt (observed 2026-07-06: a background apply sat
    # ~1h at the prompt before it was noticed). If stdin is redirected and the caller
    # did not pass -AutoApprove, stop in 2s with a clear message rather than hang.
    if ($Act -in @('apply', 'destroy') -and -not $AutoApprove -and [Console]::IsInputRedirected) {
      throw "[$L] $Act needs approval but stdin is non-interactive -- it would hang on terraform's 'yes?' prompt. Re-run with -AutoApprove: ./infra/deploy.ps1 -Action $Action -AutoApprove"
    }

    $tfArgs = @($Act, '-input=false') + $ExtraArgs
    if ($Act -in @('apply', 'destroy') -and $AutoApprove) { $tfArgs += '-auto-approve' }

    & terraform @tfArgs
    if ($LASTEXITCODE -ne 0) { throw "[$L] $Act failed -- stopping (state protection)" }
  }
  finally {
    Pop-Location
  }
}

# helm 'wait=true' can pass even when the controller fast-panics at startup
# (observed 2026-07-03: chart 1.1.1 on K8s 1.34 -> instant panic -> CrashLoopBackOff,
#  yet helm_release and terraform apply both went green). terraform green != controller
# healthy, so after the karpenter layer applies we gate on the actual Deployment rollout.
function Test-KarpenterHealth {
  if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "WARN: kubectl not found -- skipping karpenter health gate. Verify manually:" -ForegroundColor Yellow
    Write-Host "      kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter" -ForegroundColor Yellow
    return
  }

  # Resolve cluster name from the shared layer's state (no hardcoding).
  Push-Location (Join-Path $InfraRoot 'shared')
  try { $cluster = (& terraform output -raw eks_cluster_name 2>$null) } finally { Pop-Location }
  if (-not $cluster) {
    Write-Host "WARN: could not read eks_cluster_name from shared state -- skipping health gate." -ForegroundColor Yellow
    return
  }

  & aws eks update-kubeconfig --name $cluster --region ap-northeast-2 | Out-Null
  Write-Host "--- [karpenter] health gate: waiting for controller rollout (max 180s) ---" -ForegroundColor Green
  & kubectl rollout status deployment/karpenter -n kube-system --timeout=180s
  if ($LASTEXITCODE -ne 0) {
    & kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter
    & kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter --tail=20
    throw "[karpenter] controller is NOT healthy (rollout did not complete) -- terraform was green but the pod is failing. See logs above (common cause: chart version incompatible with the cluster K8s version)."
  }
  Write-Host "[karpenter] controller healthy (rollout complete)" -ForegroundColor Green
}

foreach ($l in $layers) {
  Invoke-Layer -L $l -Act $Action
  if ($l -eq 'karpenter' -and $Action -eq 'apply') { Test-KarpenterHealth }
  Write-Host ""
}

Write-Host "== done: terraform $Action ($($layers -join ', ')) ==" -ForegroundColor Cyan
if ($Action -eq 'apply') {
  Write-Host "Cost discipline: after verifying, run './infra/deploy.ps1 -Action destroy -AutoApprove'." -ForegroundColor Yellow
}
