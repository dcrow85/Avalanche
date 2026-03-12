param(
  [string]$Workspace = "C:\terrarium-v43-codex",
  [int]$Port = 8581
)

python C:\Avalanche\dashboard_v43_codex.py $Workspace --port $Port
