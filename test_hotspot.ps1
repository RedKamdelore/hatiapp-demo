# Тест включения Mobile Hotspot
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

$cp = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
Write-Output "Profil: $($cp.ProfileName)"

$tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($cp)
Write-Output "Status do: $($tm.TetheringOperationalState)"

# Задаём имя сети и пароль
$config = $tm.GetCurrentAccessPointConfiguration()
$config.Ssid = "HatiApp"
$config.Passphrase = "hatiapp2026"
$r1 = Await ($tm.ConfigureAccessPointAsync($config)) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
Write-Output "Config result: $($r1.Status)"

# Включаем
$r2 = Await ($tm.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
Write-Output "Start result: $($r2.Status)"
Write-Output "Status posle: $($tm.TetheringOperationalState)"
