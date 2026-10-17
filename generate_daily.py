"""Generate code locally, validate it in isolation, and atomically activate it."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from scenes import check_source
from classic_scenes import classic_scene, NAMES as CLASSIC_NAMES
from constrained_scene import THEMES, grammar_for, matches_spec

BASE = Path('/opt/room-visualiser')
DATA = Path('/var/lib/room-visualiser')
MODEL = Path('/opt/room-visualiser-model/qwen-coder.gguf')
CLI = Path('/opt/room-visualiser-model/llama-cli')

INSTRUCTIONS = """Write one Python audio visualiser function, code only.
Follow the supplied grammar exactly. Choose motion speed, phase, audio gain and
colour for today's theme. Keep every required definition and drawing call.
"""


def extract_code(text):
    # llama.cpp b3889 prints this diagnostic after an end-of-generation token.
    text = re.sub(r'\s*\[end of text\]\s*\Z', '', text)
    if '```' in text:
        pieces = re.findall(r'```(?:python)?\s*\n(.*?)```', text, re.S)
        text = pieces[0] if pieces else text.replace('```python', '').replace('```', '')
    definitions = list(re.finditer(r'^def\s+\w+\s*\(', text, re.M))
    if not definitions:
        raise ValueError('No drawing function returned')
    if len(definitions) != 1:
        raise ValueError('Supply exactly one drawing function')
    lines = text[definitions[0].start():].splitlines()
    header = re.fullmatch(r'def\s+\w+\s*\(([^)]*)\)\s*:\s*', lines[0])
    if header is None:
        raise ValueError('Incomplete or unsupported drawing function signature')
    arguments = [arg.strip() for arg in header.group(1).split(',')]
    if arguments not in [['draw', 't', 'audio', 'width'],
                         ['draw', 't', 'audio', 'width', 'height']]:
        raise ValueError('Drawing arguments must be draw, t, audio, width, height')
    # Normalise the entry point without changing the model's drawing body.
    # The full syntax and isolated rendering checks still run below.
    clean = ['def draw_frame(draw, t, audio, width, height):']
    for line in lines[1:]:
        if line.strip() and not line.startswith((' ', '\t')):
            break
        clean.append(line)
    result = '\n'.join(clean).strip()+'\n'
    check_source(result)
    return result


def sandbox(command, name, memory='256M', seconds=30):
    return ['systemd-run', '--quiet', '--wait', '--pipe', '--collect',
            '--unit='+name, '--uid=visdisplay', '-p', 'PrivateNetwork=yes',
            '-p', 'PrivateDevices=yes', '-p', 'ProtectHome=yes',
            '-p', 'ProtectSystem=strict', '-p', 'NoNewPrivileges=yes',
            '-p', 'MemoryMax='+memory, '-p', 'LimitAS='+memory,
            '-p', 'RuntimeMaxSec='+str(seconds),
            '-p', 'Environment=OPENBLAS_NUM_THREADS=1', *command]


def run_model(command, seconds=2700):
    output = DATA/'last-model-output.txt'
    diagnostics = DATA/'last-model-stderr.txt'
    with output.open('w') as out, diagnostics.open('w') as err:
        result = subprocess.run(sandbox(command, 'vis-model', '800M', seconds),
                                stdout=out, stderr=err, timeout=seconds+30)
    text = output.read_text()
    if result.returncode == 0 and not matches_spec(extract_code(text), datetime.date.today()):
        raise ValueError('Incomplete or nonconforming constrained scene')
    return subprocess.CompletedProcess(command, result.returncode,
                                       text, diagnostics.read_text())


def activate_scene(code, date, theme, status):
    check_source(code)
    status_path = DATA/'generation.json'
    current = DATA/'current.py'
    if current.exists() and current.read_text().strip() == code.strip():
        raise ValueError('This repeats the current scene. Use a different layout and colours.')
    candidate = DATA/'candidate.py'
    candidate.write_text(code)
    candidate.chmod(0o644)
    checked = subprocess.run(sandbox(['/usr/bin/python3', str(BASE/'validate_scene.py'),
                                      str(candidate)], 'vis-validate'),
                             capture_output=True, text=True, timeout=35)
    if checked.returncode:
        raise RuntimeError(checked.stderr[-800:])
    history = DATA/'history'
    history.mkdir(exist_ok=True)
    (history/(date+'.py')).write_text(code)
    if current.exists():
        (DATA/'previous.py').write_text(current.read_text())
    os.replace(str(candidate), str(current))
    status.pop('error', None)
    status.update(success=True, theme=theme, sha256=hashlib.sha256(code.encode()).hexdigest(),
                  validation=checked.stdout.strip())
    status_path.write_text(json.dumps(status, indent=2))
    print('Scene accepted: '+theme+' ('+status.get('source', 'local_model')+')', flush=True)


def activate_fallback(date, status):
    """Try validated classics, avoiding the previous accepted theme."""
    status['model_error'] = status.get('error', 'Model generation failed')
    status['source'] = 'classic_fallback'
    status['model_success'] = False
    failures = []
    day = datetime.date.fromisoformat(date)
    for offset in range(len(CLASSIC_NAMES)):
        theme, code = classic_scene(day, offset)
        if theme == status.get('previous_theme'):
            continue
        try:
            activate_scene(code, date, theme, status)
            return
        except (ValueError, SyntaxError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            failures.append(str(exc)[:300])
    status.update(success=False, error='Classic fallbacks failed: '+'; '.join(failures))
    (DATA/'generation.json').write_text(json.dumps(status, indent=2))
    raise SystemExit(1)


def run(force=False, retry_saved=False):
    os.environ['TZ'] = 'Europe/London'
    time.tzset()
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA/'generation.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Generation already running')
            return
        date = datetime.date.today().isoformat()
        status_path = DATA/'generation.json'
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
        if retry_saved:
            if status.get('date') != date:
                raise ValueError('Saved output must belong to today')
            if status.get('success') and status.get('source') != 'classic_fallback':
                print('Today already has an accepted scene')
                return
            code = extract_code((DATA/'last-model-output.txt').read_text())
            if (status.get('generation_format') == 'constrained_python_v1'
                    and not matches_spec(code, datetime.date.today())):
                raise ValueError('Saved output does not match the constrained scene')
            original_status = status.copy()
            status['recovered_from_saved_output'] = True
            status['source'] = 'local_model'
            status.pop('model_success', None)
            theme = THEMES[datetime.date.today().toordinal() % len(THEMES)]
            try:
                activate_scene(code, date, theme, status)
            except (ValueError, SyntaxError, RuntimeError, subprocess.TimeoutExpired) as exc:
                if original_status.get('success'):
                    original_status['recovery_error'] = str(exc)[:1000]
                    status_path.write_text(json.dumps(original_status, indent=2))
                    raise
                status['error'] = str(exc)[:1000]
                status_path.write_text(json.dumps(status, indent=2))
                raise
            return
        if not force and status.get('date') == date:
            if not status.get('success'):
                activate_fallback(date, status)
                return
            print('Already attempted today; keeping current scene')
            return
        if not force and datetime.datetime.now().hour >= 6:
            print('Outside generation window; waiting until tonight')
            return
        previous_theme = status.get('theme') if status.get('success') else status.get('previous_theme')
        status = {'date': date, 'success': False, 'attempts': 0,
                  'previous_theme': previous_theme, 'source': 'local_model',
                  'generation_format': 'constrained_python_v1'}
        status_path.write_text(json.dumps(status))
        theme = THEMES[datetime.date.today().toordinal() % len(THEMES)]
        _, grammar = grammar_for(datetime.date.today())
        (DATA/'scene.gbnf').write_text(grammar)
        errors = ''
        for attempt in range(2):
            now = datetime.datetime.now()
            seconds = 2700 if force else min(2700, int((now.replace(hour=6, minute=0, second=0) - now).total_seconds()))
            if seconds <= 0:
                status['error'] = 'Generation window ended; keeping current scene'
                status_path.write_text(json.dumps(status, indent=2))
                break
            status['attempts'] = attempt+1
            status_path.write_text(json.dumps(status, indent=2))
            prompt = ('<|im_start|>system\n'+INSTRUCTIONS+'<|im_end|>\n'
                      '<|im_start|>user\nToday: '+date+'. Theme: '+theme+'. '
                      +errors+
                      '\nWrite the function now.<|im_end|>\n<|im_start|>assistant\n')
            (DATA/'prompt.txt').write_text(prompt)
            try:
                command = [str(CLI), '-m', str(MODEL), '-f', str(DATA/'prompt.txt'),
                           '-c', '2048', '-n', '600', '-t', '3', '-b', '64',
                           '--grammar-file', str(DATA/'scene.gbnf'),
                           '--temp', '0.65', '--seed', str(int(time.time()) % 2147483647),
                           '--no-display-prompt']
                generated = run_model(command, seconds)
                if generated.returncode:
                    raise RuntimeError('Model process failed: '+generated.stderr[-800:])
                code = extract_code(generated.stdout)
                activate_scene(code, date, theme, status)
                return
            except (ValueError, SyntaxError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                errors = 'Previous attempt failed: '+str(exc)[:300]+'. Simplify the code.'
                status['error'] = str(exc)[:1000]
                status_path.write_text(json.dumps(status, indent=2))
                print('Attempt failed; keeping existing scene: '+str(exc)[:300], flush=True)
        activate_fallback(date, status)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--retry-saved', action='store_true',
                        help='Revalidate today\'s failed output without running the model again')
    args = parser.parse_args()
    run(force=args.force, retry_saved=args.retry_saved)
