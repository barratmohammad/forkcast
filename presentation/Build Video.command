#!/bin/bash
# Double-click to build the final video with your recorded voice (Docker + Ollama must be running).
cd "$(dirname "$0")" || exit 1
.venv/bin/python make_demo.py --narration narration --gap 2.0 && open forkcast_presentation.mp4
echo
read -r -p "Press Enter to close this window."
