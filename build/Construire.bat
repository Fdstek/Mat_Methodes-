@echo off
rem Double-clic : construit MatMethode.exe (la fenetre reste ouverte a la fin).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
