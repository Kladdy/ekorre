#!/bin/bash
export PYENV_ROOT="/root/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

cd /app

# Create and activate the virtual environment
./install_venv_no_pyenv.sh
source ekorre-venv/bin/activate

# Run your Python app
python3 src/main.py

# export NICEGUI_PORT="12345"; python3 src/main.py
# export NICEGUI_PORT="12345"; export NO_FETCH_REACTOR_DATA="1"; python3 src/main.py