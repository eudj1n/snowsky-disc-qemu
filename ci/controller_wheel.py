"""Build an sdist/wheel and test the installed core without repository imports."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile


def main():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='disc-wheel-') as directory:
        root = Path(directory)
        source = root / 'source'
        shutil.copytree(repo / 'controller', source,
                        ignore=shutil.ignore_patterns('__pycache__', 'build', 'dist', '*.egg-info'))
        subprocess.run([sys.executable, '-m', 'build', '--no-isolation', '--outdir', str(root / 'dist')],
                       cwd=source, check=True)
        wheel, = (root / 'dist').glob('*.whl')
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            assert 'controller/py.typed' in names
            assert 'controller/bridge/ws_console.html' in names
            assert not any('/tests/' in name or name.startswith(('research/', 'emulator/', 'viewer/'))
                           for name in names)
        environment = root / 'venv'
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        subprocess.run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel)],
                       cwd=root, check=True)
        # Only the synthetic peer is copied; no source controller package is visible.
        fixture = root / 'session_fixture.py'
        shutil.copyfile(repo / 'controller/tests/session_fixture.py', fixture)
        smoke = root / 'wheel_smoke.py'
        shutil.copyfile(repo / 'ci/controller_wheel_smoke.py', smoke)
        subprocess.run([str(python), '-I', str(smoke), str(fixture)], cwd=root, check=True,
                       env={key: value for key, value in os.environ.items() if key != 'PYTHONPATH'})
        subprocess.run([str(python), '-I', '-m', 'pip', 'install', '--constraint',
                        str(repo / 'ci/requirements-quality.txt'), str(wheel) + '[websocket,bridge]'],
                       cwd=root, check=True)
        subprocess.run([str(python), '-I', '-c',
                        'import controller.fiio_ws, controller.bridge.ws_bridge; '
                        'from importlib.metadata import version; '
                        'assert version("aiohttp") == "3.12.15"'], cwd=root, check=True)
        print('Controller sdist → wheel → isolated core installation and synthetic session: PASS')
        print('Installed WebSocket/bridge extras and optional imports: PASS')


if __name__ == '__main__':
    main()
