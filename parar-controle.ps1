Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*lol_controle.py*' -and $_.Name -like 'python*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
