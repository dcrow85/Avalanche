param(
  [string]$Workspace = "C:\terrarium-v43",
  [string]$Model = "gpt-4o",
  [int]$MaxCycles = 20,
  [ValidateSet("first-failure", "adversarial")]
  [string]$OracleMode = "first-failure"
)

python C:\Avalanche\hypervisor_v43.py --workspace $Workspace --model $Model --max-cycles $MaxCycles --oracle-mode $OracleMode
