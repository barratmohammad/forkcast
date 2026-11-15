#!/bin/bash
# Double-click to record the ForkCast narration, one line at a time.
cd "$(dirname "$0")" || exit 1
echo "ForkCast narration recorder"
echo
read -r -p "Start over from line 1 and replace every clip? (y = start over, Enter = continue where you left off) " ans
if [[ "$ans" =~ ^[Yy] ]]; then
  rm -f narration/*.wav
  echo "Cleared old clips. Starting at line 1."
fi
.venv/bin/python record_narration.py
echo
read -r -p "Press Enter to close this window."
