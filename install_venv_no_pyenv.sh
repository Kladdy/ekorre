set -euo pipefail

venv_path="ekorre-venv"

# Check if the virtual environment already exists
if [ -d $venv_path ]; then
    echo "Virtual environment already exists at path '$venv_path'. Please remove it first if the intention is to recreate the venv."
    exit 1
fi

echo "Using Python version $(python3 --version)"
echo "Creating virtual environment at path '$venv_path'"

# Create the virtual environment
python3 -m venv $venv_path

# Activate the virtual environment
. $venv_path/bin/activate

# Install the required packages
python -m pip install -r requirements.txt

echo "✓ Done! Activate using '. $venv_path/bin/activate'"
