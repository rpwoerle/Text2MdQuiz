@echo off


if "%~1"=="" (
    echo Usage: runapp.cmd ^<files_or_globs^> [options]
    echo Examples:
    echo   runapp.cmd .\texts\*.txt
    echo   runapp.cmd "C:\recordings\**\*.txt" --overwrite
    goto :EOF
)

if exist C:\Tools\setpyver.cmd (
    call C:\Tools\setpyver 3.14
) else if exist C:\Users\ralph\Tools\setpyver.cmd (
    call C:\Users\ralph\Tools\setpyver 3.14
) else (
    echo No setpyver.cmd found
    goto :EOF
)

python %~dp0text2mdquiz.py %*

