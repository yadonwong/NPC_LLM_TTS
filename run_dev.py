import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'


def py(name: str):
    if platform.system() == 'Windows':
        return str(VENV / 'Scripts' / f'{name}.exe')
    return str(VENV / 'bin' / name)


def main():
    if not VENV.exists():
        subprocess.check_call([sys.executable, str(ROOT / 'bootstrap.py')], cwd=ROOT)
    os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
    python = py('python')
    subprocess.check_call([python, '-m', 'app.main'], cwd=ROOT)


if __name__ == '__main__':
    main()
