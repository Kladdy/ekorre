set -euo pipefail

venv_path="ekorre-venv"
python_version="3.12.9"

# Check if the virtual environment already exists
if [ -d $venv_path ]; then
    echo "Virtual environment already exists at path '$venv_path'. Please remove it first if the intention is to recreate the venv."
    exit 1
fi

# Install Python version using pyenv if not already installed
if ! pyenv versions | grep -q $python_version; then
    echo "Installing Python $python_version using pyenv..."
    pyenv install $python_version
else
    echo "Python $python_version is already installed."
fi

# Create the virtual environment
$(pyenv root)/versions/$python_version/bin/python3 -m venv $venv_path

# Activate the virtual environment
. $venv_path/bin/activate

# Install the required packages
python -m pip install -r requirements.txt

echo "✓ Done! Activate using '. $venv_path/bin/activate'"
