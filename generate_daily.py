"""Select a built-in classic scene, validate it, and atomically activate it."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from classic_series import scheduled_scene
from scenes import check_source

BASE = Path('/opt/room-visualiser')
DATA = Path('/var/lib/room-visualiser')


def sandbox(command, name, memory='256M', seconds=30):
    return ['systemd-run', '--quiet', '--wait', '--pipe', '--collect',
            '--unit='+name, '--uid=visdisplay', '-p', 'PrivateNetwork=yes',
            '-p', 'PrivateDevices=yes', '-p', 'ProtectHome=yes',
            '-p', 'ProtectSystem=strict', '-p', 'NoNewPrivileges=yes',
            '-p', 'MemoryMax='+memory, '-p', 'LimitAS='+memory,
            '-p', 'RuntimeMaxSec='+str(seconds),
            '-p', 'Environment=OPENBLAS_NUM_THREADS=1', *command]


def activate_scene(code, date, theme, status):
    check_source(code)
    status_path = DATA/'generation.json'
    current = DATA/'current.py'
    candidate = DATA/'candidate.py'
    candidate.write_text(code)
    candidate.chmod(0o644)
    validation_command = ['/usr/bin/python3', str(BASE/'validate_scene.py'), str(candidate)]
    if status.get('source') in ('manual', 'classic_series') and status.get('animation_mode') == 'audio_driven':
        validation_command.append('--audio-driven')
    checked = subprocess.run(sandbox(validation_command, 'vis-validate'),
                             capture_output=True, text=True, timeout=35)
    if checked.returncode:
        raise RuntimeError(checked.stderr[-800:])
    history = DATA/'history'
    history.mkdir(exist_ok=True)
    (history/(date+'.py')).write_text(code)
    if current.exists() and current.read_text() != code:
        (DATA/'previous.py').write_text(current.read_text())
    os.replace(str(candidate), str(current))
    status.pop('error', None)
    status.update(success=True, theme=theme, sha256=hashlib.sha256(code.encode()).hexdigest(),
                  validation=checked.stdout.strip())
    status_path.write_text(json.dumps(status, indent=2))
    print('Scene accepted: '+theme+' ('+status.get('source', 'classic_series')+')', flush=True)


def run(force=False):
    os.environ['TZ'] = 'Europe/London'
    time.tzset()
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA/'generation.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Scene selection already running')
            return
        day = datetime.date.today()
        date = day.isoformat()
        status_path = DATA/'generation.json'
        try:
            previous = json.loads(status_path.read_text())
        except (FileNotFoundError, ValueError):
            previous = {}
        theme, code = scheduled_scene(day)
        current = DATA/'current.py'
        if (not force and previous.get('date') == date
                and previous.get('success')
                and previous.get('source') == 'classic_series'
                and current.exists() and current.read_text() == code):
            print('Today already has its classic scene')
            return
        status = {'date': date, 'source': 'classic_series',
                  'animation_mode': 'audio_driven', 'success': False,
                  'previous_theme': previous.get('theme'), 'attempts': 0}
        try:
            activate_scene(code, date, theme, status)
        except (ValueError, SyntaxError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            status['error'] = str(exc)[:1000]
            status_path.write_text(json.dumps(status, indent=2))
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true',
                        help="Revalidate and activate today's built-in scene")
    args = parser.parse_args()
    run(force=args.force)
