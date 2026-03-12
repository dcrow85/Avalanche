param(
  [string]$Workspace = "C:\terrarium-v43",
  [int]$Port = 8481
)

python C:\Avalanche\dashboard.py $Workspace --port $Port
