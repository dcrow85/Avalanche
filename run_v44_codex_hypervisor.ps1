param(
  [string]$Workspace = "C:\terrarium-v44-codex",
  [ValidateSet("gpt-5.4", "gpt-5.3-codex", "gpt-5.1-codex-mini")]
  [string]$Model = "gpt-5.3-codex",
  [int]$MaxCycles = 20,
  [int]$ContinueCycles = 0,
  [ValidateSet("first-failure", "adversarial")]
  [string]$OracleMode = "first-failure"
)

$env:AVALANCHE_CODEX_MODEL = $Model
python C:\Avalanche\hypervisor_v44_codex.py --workspace $Workspace --model $Model --max-cycles $MaxCycles --continue-cycles $ContinueCycles --oracle-mode $OracleMode
