import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def run(cmd, cwd=None):
    print('>>', ' '.join(cmd))
    subprocess.check_call(cmd, cwd=cwd or ROOT)


def pybin(name: str):
    if platform.system() == 'Windows':
        return str(VENV / 'Scripts' / f'{name}.exe')
    return str(VENV / 'bin' / name)


def ensure_venv():
    if not VENV.exists():
        run([sys.executable, '-m', 'venv', str(VENV)])


def main():
    if not (3, 10) <= sys.version_info[:2] < (3, 13):
        raise RuntimeError(
            f"Python 版本不兼容: {sys.version.split()[0]}。请使用 Python 3.10~3.12 运行 bootstrap.py"
        )

    ensure_venv()
    pip = pybin('pip')
    run([pip, 'install', '--upgrade', 'pip', 'wheel'])
    run([pip, 'install', 'setuptools<82'])
    run([pip, 'install', '-r', str(ROOT / 'requirements.txt')])

    # Ensure VoxCPM repo exists
    third_party = ROOT / 'third_party' / 'VoxCPM'
    if not third_party.exists():
        run(['git', 'clone', 'https://github.com/OpenBMB/VoxCPM', str(third_party)])

    # Install VoxCPM package into project venv
    run([pip, 'install', '-e', str(third_party)])

    # Ensure IndexTTS repo exists
    indextts_repo = ROOT / 'third_party' / 'index-tts'
    if not indextts_repo.exists():
        run(['git', 'clone', 'https://github.com/index-tts/index-tts', str(indextts_repo)])

    # Install IndexTTS package into project venv
    run([pip, 'install', '-e', str(indextts_repo)])

    print('Bootstrap complete.')


if __name__ == '__main__':
    main()
