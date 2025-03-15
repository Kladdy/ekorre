venv_path="ekorre-venv"

if [ -d $venv_path ]; then
    echo "Virtual environment already exists at path '$venv_path'. Please remove it first if the intention is to recreate the venv."
    exit 1
fi

python3 -m venv $venv_path
. $venv_path/bin/activate

python3 -m pip install -r requirements.txt

echo ✓ Done! Activate using '. $venv_path/bin/activate'