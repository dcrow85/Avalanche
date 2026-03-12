param(
  [string]$Workspace = "C:\terrarium-v44-codex",
  [int]$Port = 8981
)

python C:\Avalanche\dashboard_v44_codex.py $Workspace --port $Port
