@echo off
setlocal DisableDelayedExpansion
set "ASIDE_JEV_SOURCE=%~dp0"
if not defined ASIDE_JEV_INSTALL_DIR set "ASIDE_JEV_INSTALL_DIR=%LOCALAPPDATA%\AsideJev"
if not defined LOCALAPPDATA goto failed
set "ASIDE_JEV_UV_ARCH=x86_64"
set "ASIDE_JEV_UV_SHA=a252121d5b59398fcb137c6ea448176459a44010f33f67e0072305a637119ca7"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ASIDE_JEV_UV_ARCH=aarch64"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ASIDE_JEV_UV_SHA=3e1aa6849d77f0e00dc865e4afab5c5b32de053e21fe35bf5ad5cec3734ec976"
echo Preparing Aside Jev for Windows...
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; $root=$env:ASIDE_JEV_INSTALL_DIR; foreach($child in @('','.installer-owned','bin','bin\uv.exe','python','cache','runtime','runtime\Scripts','requirements.lock.txt')) { $check=if($child){Join-Path $root $child}else{$root}; if((Test-Path -LiteralPath $check) -and ((Get-Item -LiteralPath $check -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Linked installation path is not supported'} }; if(Test-Path -LiteralPath $root){if(((Get-Item -LiteralPath $root).Attributes -band [IO.FileAttributes]::ReparsePoint) -or (!(Test-Path -LiteralPath (Join-Path $root '.installer-owned')) -or (Get-Content -LiteralPath (Join-Path $root '.installer-owned') -Raw).Trim() -ne 'aside-jev installer v1')){throw 'Installation folder is not owned by Aside Jev'}}; New-Item -ItemType Directory -Force -Path $root | Out-Null; Set-Content -LiteralPath (Join-Path $root '.installer-owned') -Value 'aside-jev installer v1'; $temp=Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString()); New-Item -ItemType Directory -Path $temp | Out-Null; try { $zip=Join-Path $temp 'uv.zip'; Invoke-WebRequest -UseBasicParsing -Uri ('https://github.com/astral-sh/uv/releases/download/0.12.17/uv-'+$env:ASIDE_JEV_UV_ARCH+'-pc-windows-msvc.zip') -OutFile $zip; $sha=[Security.Cryptography.SHA256]::Create(); try { $stream=[IO.File]::OpenRead($zip); try { $actualSha=[BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() } finally { $stream.Dispose() } } finally { $sha.Dispose() }; if($actualSha -cne $env:ASIDE_JEV_UV_SHA){throw 'Download checksum failed'}; [void][Reflection.Assembly]::Load('System.IO.Compression.FileSystem, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089'); [IO.Compression.ZipFile]::ExtractToDirectory($zip,$temp); $uv=Get-ChildItem -LiteralPath $temp -Filter uv.exe -Recurse | Select-Object -First 1; if(!$uv){throw 'uv.exe missing'}; New-Item -ItemType Directory -Force -Path (Join-Path $root 'bin') | Out-Null; Copy-Item -LiteralPath $uv.FullName -Destination (Join-Path $root 'bin\uv.exe') -Force } finally {Remove-Item -LiteralPath $temp -Recurse -Force}"
if errorlevel 1 goto failed
set "UV_PYTHON_INSTALL_DIR=%ASIDE_JEV_INSTALL_DIR%\python"
set "UV_PYTHON_BIN_DIR=%ASIDE_JEV_INSTALL_DIR%\bin"
set "UV_CACHE_DIR=%ASIDE_JEV_INSTALL_DIR%\cache"
set "UV_NO_MODIFY_PATH=1"
set "ASIDE_JEV_UV=%ASIDE_JEV_INSTALL_DIR%\bin\uv.exe"
set "ASIDE_JEV_PYTHON=%ASIDE_JEV_INSTALL_DIR%\runtime\Scripts\python.exe"
if exist "%ASIDE_JEV_PYTHON%" goto package
"%ASIDE_JEV_UV%" venv --python 3.11 "%ASIDE_JEV_INSTALL_DIR%\runtime"
if errorlevel 1 goto failed
:package
"%ASIDE_JEV_UV%" export --project "%ASIDE_JEV_SOURCE%." --frozen --no-dev --no-emit-project --format requirements-txt --output-file "%ASIDE_JEV_INSTALL_DIR%\requirements.lock.txt" >nul
if errorlevel 1 goto failed
"%ASIDE_JEV_UV%" pip install --python "%ASIDE_JEV_PYTHON%" --require-hashes --requirements "%ASIDE_JEV_INSTALL_DIR%\requirements.lock.txt"
if errorlevel 1 goto failed
"%ASIDE_JEV_UV%" pip install --python "%ASIDE_JEV_PYTHON%" --no-deps --reinstall-package aside-jev "%ASIDE_JEV_SOURCE%."
if errorlevel 1 goto failed
"%ASIDE_JEV_PYTHON%" -I -X utf8 -m aside_jev.cli setup %*
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Installation did not finish. Review the error above, then retry.
pause
exit /b 1
