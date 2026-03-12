param(
  [string]$Workspace = "C:\terrarium-v44-raw",
  [string]$Model = "qwen/qwen3-coder",
  [string]$ApiBase = "https://api.haimaker.ai/v1",
  [string]$ApiKeyEnv = "HAIMAKER_API_KEY",
  [int]$MaxCycles = 20,
  [ValidateSet("first-failure", "adversarial")]
  [string]$OracleMode = "first-failure",
  [ValidateSet("json_schema", "json_object")]
  [string]$ResponseFormat = "json_object"
)

python C:\Avalanche\hypervisor_v44.py --workspace $Workspace --model $Model --api-base $ApiBase --api-key-env $ApiKeyEnv --response-format $ResponseFormat --max-cycles $MaxCycles --oracle-mode $OracleMode
