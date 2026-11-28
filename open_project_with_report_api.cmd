@echo off
call "%~dp0open_project.cmd" -ReportApi %*
exit /b %ERRORLEVEL%
