param(
    [string]$Workspace = "C:\terrarium-codex",
    [ValidateSet("gpt-5.4", "gpt-5.3-codex", "gpt-5.1-codex-mini")]
    [string]$Model = "gpt-5.3-codex"
)

$env:AVALANCHE_CODEX_MODEL = $Model
python C:\Avalanche\hypervisor_codex.py --workspace $Workspace --model $Model
