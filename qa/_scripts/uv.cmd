@echo off
rem QA wrapper: emulate `uv run X ...` by running X through the backend venv python.
rem Used only for local QA (uv is not installed on this machine). Not part of the project.
setlocal enabledelayedexpansion
set "args="
set /a i=0
for %%a in (%*) do (
  set /a i+=1
  if !i! gtr 1 set "args=!args! %%a"
)
"D:\workspace\ai\BetterOneself\backend\.venv\Scripts\python.exe" -m !args!
