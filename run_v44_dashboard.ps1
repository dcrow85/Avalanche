param(
  [string]$Workspace = "C:\terrarium-v44",
  [int]$Port = 8381
)

python C:\Avalanche\dashboard_v44.py $Workspace --port $Port
