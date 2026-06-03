import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'


def py(name: str):
    if platform.system() == 'Windows':
        return str(VENV / 'Scripts' / f'{name}.exe')
    return str(VENV / 'bin' / name)


def main():
    pyinstaller = py('pyinstaller')
    cmd = [
        pyinstaller,
        '--noconfirm',
        '--windowed',
        '--name', 'NPC_LLM_TTS',
        '--add-data', f"{ROOT / 'app' / 'ui' / 'style.qss}{';' if platform.system() == 'Windows' else ':'}app/ui",
        str(ROOT / 'app' / 'main.py'),
    ]
    subprocess.check_call(cmd, cwd=ROOT)


if __name__ == '__main__':
    main()
