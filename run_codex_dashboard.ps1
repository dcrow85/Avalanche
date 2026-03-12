param(
    [string]$Workspace = "C:\terrarium-codex",
    [int]$Port = 8281
)

python C:\Avalanche\dashboard.py $Workspace --port $Port
