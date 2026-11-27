"""Manage the local services behind the development gateway on port 8000."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'logs' / 'local_services.json'
SERVICES = {
    'main': (8100, ROOT / '.venv/Scripts/python.exe', [str(ROOT / 'app.py')]),
    'xiaoha': (8501, ROOT / '.venv-xiaoha/Scripts/python.exe', [
        '-m', 'streamlit', 'run', str(ROOT / 'Department/视觉设计部/xiaoha/openrouter_image_site.py'),
        '--server.address', '127.0.0.1', '--server.port', '8501',
        '--server.baseUrlPath', 'lashforge', '--server.headless', 'true',
        '--server.fileWatcherType', 'none',
    ]),
    'xiaoha-static': (8502, ROOT / '.venv-xiaoha/Scripts/python.exe', [str(ROOT / 'docker/xiaoha_static.py')]),
    'gateway': (8000, Path(shutil.which('node') or 'node.exe'), [str(ROOT / 'scripts/local_gateway.mjs')]),
}


def listening(port):
    with socket.socket() as client:
        client.settimeout(.5)
        return client.connect_ex(('127.0.0.1', port)) == 0


def read_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding='utf-8'))
    return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.replace(STATE)


def process_command(pid):
    result = subprocess.run([
        'powershell', '-NoProfile', '-Command',
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}').CommandLine",
    ], capture_output=True, text=True, errors='replace', check=True)
    return result.stdout.strip()


def stop(name, state):
    pid = state.get(name)
    if not pid:
        print(f'{name}: no managed process; existing external services are left running')
        return
    command = process_command(pid)
    executable = str(SERVICES[name][1]).lower()
    script = next(arg for arg in SERVICES[name][2] if Path(arg).is_absolute()).lower()
    if command and (executable not in command.lower() or script not in command.lower()):
        raise RuntimeError(f'{name}: PID {pid} now belongs to another process; refusing to stop')
    if command:
        subprocess.run(['taskkill', '/PID', str(int(pid)), '/T', '/F'], check=True)
    state.pop(name, None)
    save_state(state)


def start(name, state):
    port, executable, arguments = SERVICES[name]
    if listening(port):
        if name == 'gateway' and not state.get(name):
            raise RuntimeError('Port 8000 is already in use. Stop the previous local launcher first.')
        print(f'{name}: port {port} already listening; no duplicate process started')
        return
    if not executable.exists():
        raise RuntimeError(f'Executable missing: {executable}')
    child_env = os.environ.copy()
    child_env.update(
        TC_SINGLE_PORT='1',
        TC_WEB_HOST='127.0.0.1',
        TC_WEB_PORT='8100',
        LASHFORGE_SERVER_ADDRESS='127.0.0.1',
        LASHFORGE_PUBLIC_APP_URL='http://localhost:8000/lashforge',
        JIMENG_PUBLIC_UPLOAD_BASE_URL='http://localhost:8000/jimeng_uploads',
    )
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with (STATE.parent / f'{name}.stdout.log').open('ab') as out, (STATE.parent / f'{name}.stderr.log').open('ab') as err:
        process = subprocess.Popen([str(executable), *arguments], cwd=ROOT, stdout=out, stderr=err, env=child_env,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    state[name] = process.pid
    save_state(state)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{name}: exited during startup; see logs/{name}.stderr.log')
        if listening(port):
            print(f'{name}: ready on port {port}, PID {process.pid}')
            return
        time.sleep(.25)
    raise RuntimeError(f'{name}: startup timed out; process retained for diagnosis')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status'])
    parser.add_argument('--service', choices=['all', *SERVICES], default='all')
    args = parser.parse_args()
    state = read_state()
    names = list(SERVICES) if args.service == 'all' else [args.service]
    if args.action in ('start', 'restart') and 'gateway' in names and listening(8000) and not state.get('gateway'):
        parser.exit(1, 'Port 8000 is already in use. Stop the previous local launcher first.\n')
    for name in names:
        if args.action in ('stop', 'restart'):
            stop(name, state)
        if args.action in ('start', 'restart'):
            start(name, state)
        if args.action == 'status':
            print(f'{name}: port={SERVICES[name][0]}, listening={listening(SERVICES[name][0])}, managed_pid={state.get(name)}')


if __name__ == '__main__':
    main()
