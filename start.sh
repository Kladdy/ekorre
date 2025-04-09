#!/bin/bash
export PYENV_ROOT="/root/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

cd /app

# Create and activate the virtual environment
./install_venv.sh
source ekorre-venv/bin/activate

# Run your Python app
python3 src/main.py
