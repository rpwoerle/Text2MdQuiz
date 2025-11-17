@echo off

if exist C:\Tools\setpyver.cmd (
    call C:\Tools\setpyver 3.14
) else if exist C:\Users\ralph\Tools\setpyver.cmd (
    call C:\Users\ralph\Tools\setpyver 3.14
) else (
    echo No setpyver.cmd found
    goto :EOF
)
start "" /B cmd /K code .