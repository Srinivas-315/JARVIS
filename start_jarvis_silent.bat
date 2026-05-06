@echo off
:: JARVIS — Silent background launcher (no console window)
:: Use pythonw to run without a terminal window
cd /d "%~dp0"
start /min pythonw main.py --wake
