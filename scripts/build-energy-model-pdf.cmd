@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-energy-model-pdf.ps1" %*
