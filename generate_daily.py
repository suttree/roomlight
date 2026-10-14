"""Generate code locally, validate it in isolation, and atomically activate it."""
import argparse
import colorsys
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

BASE = Path('/opt/room-visualiser')
DATA = Path('/var/lib/room-visualiser')
MODEL = Path('/opt/room-visualiser-model/qwen-coder.gguf')
CLI = Path('/opt/room-visualiser-model/llama-cli')

INSTRUCTIONS = '''Write a tiny animated Python drawing function. Output code only, no comments.
Use the exact function signature shown below. Keep the whole function under 12 lines.
The canvas is 360 by 360. t is time in seconds. audio['level'] and audio['pulse']
are numbers between 0 and 1. audio['quiet'] is a bool. Use pulse when quiet.
Only use math.sin, math.cos, math.pi, range, int, min, max and draw.line or draw.ellipse.
No imports or other functions. RGB colours must be integer tuples from 0 to 255.
Use at most 24 shapes. Keep all coordinates within the screen.
Here is a working example. Write a DIFFERENT composition for the requested theme:
def draw_frame(draw, t, audio, width, height):
    strength = audio['pulse'] if audio['quiet'] else audio['level']
    for i in range(12):
        angle = i * math.pi / 6 + t * 0.4
        x = 180 + 90 * math.cos(angle)
        y = 180 + 90 * math.sin(angle)
        r = 3 + 12 * strength
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(60, 210, 180))
'''
THEMES = ['orbiting moons', 'sound ripples', 'a geometric flower',
          'a constellation', 'waves', 'a spiral of dots',
          'rotating spokes', 'falling rain', 'woven lines',
          'a slowly breathing sun', 'dancing columns', 'radial sparks']


def design_brief(day):
    """Give the tiny model concrete geometry, varying it deterministically each day."""
    seed = day.toordinal()
    count = 10 + seed % 13
    speed = 20 + seed % 41
    colour = tuple(int(c*255) for c in colorsys.hsv_to_rgb((seed*.61803398875) % 1, .65, 1))
    forms = [
        'Draw orbiting dots. angle=i*2*math.pi/N+t*0.3; radius=55+i*4+20*strength. '
        'Place dots at (180+radius*math.cos(angle),180+radius*math.sin(angle)), size 3+6*strength.',
        'Draw expanding circle outlines centred at (180,180). '
        'radius=10+(i*13+t*SPEED)%150. Use outline=COLOUR and width=2, no fill.',
        'Draw a radial flower of lines from (180,180). angle=i*2*math.pi/N+t*0.15. '
        'radius=60+60*strength+25*math.sin(t+i). End at (180+radius*math.cos(angle),180+radius*math.sin(angle)).',
        'Draw dots at x=20+(i*43)%320, y=180+100*math.sin(t*0.5+i*0.7). Size 2+10*strength.',
        'Draw short horizontal wave lines. x=10+i*320/N; y=180+70*math.sin(t+i*0.5). '
        'Draw from (x,y) to (x+8,y+25*strength), width=3.',
        'Draw spiral dots. angle=i*0.65+t*0.3; radius=10+i*5. '
        'Place dots at (180+radius*math.cos(angle),180+radius*math.sin(angle)), size 2+8*strength.',
        'Draw rotating spokes. angle=i*2*math.pi/N-t*0.4. '
        'Draw from (180+40*math.cos(angle),180+40*math.sin(angle)) '
        'to (180+(90+50*strength)*math.cos(angle),180+(90+50*strength)*math.sin(angle)), width=2.',
        'Replace the example with falling rain. Use vertical lines, not circles. '
        'For each i, x=10+i*320/N; y=(t*SPEED+i*31)%300. '
        'Draw from (x,y) to (x,y+5+30*strength), width=2. Remove angle, sin and cos.',
        'Draw woven lines. y=15+i*320/N. '
        'Draw from (20,y) to (340,180+120*math.sin(t*0.4+i*0.25)*(.3+strength*.7)), width=2.',
        'Draw concentric breathing circle outlines at (180,180). '
        'radius=10+i*5+15*strength+5*math.sin(t). Use outline=COLOUR, width=2, no fill.',
        'Draw vertical sound columns as thick lines. x=15+i*320/N; '
        'h=10+140*strength*(.5+.5*math.sin(t+i)). Draw from (x,300) to (x,300-h), width=6.',
        'Draw radial sparks as short lines. angle=i*2*math.pi/N; radius=30+(t*SPEED+i*9)%100. '
        'Draw from (180+radius*math.cos(angle),180+radius*math.sin(angle)) '
        'to (180+(radius+5+20*strength)*math.cos(angle),180+(radius+5+20*strength)*math.sin(angle)), width=2.'
    ]
    return (forms[seed % len(forms)]
            .replace('N', str(count)).replace('SPEED', str(speed)).replace('COLOUR', str(colour))
            + ' Use for i in range('+str(count)+') and RGB colour '+str(colour)
            + '. Keep the strength line. Output only the rewritten function.')


def extract_code(text):
    if '```' in text:
        pieces = re.findall(r'```(?:python)?\s*\n(.*?)```', text, re.S)
        text = pieces[0] if pieces else text.replace('```python', '').replace('```', '')
    start = text.find('def draw_frame(')
    if start < 0:
        raise ValueError('No drawing function returned')
    lines = text[start:].splitlines()
    clean = [lines[0]]
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
    return subprocess.CompletedProcess(command, result.returncode,
                                       output.read_text(), diagnostics.read_text())


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
    print('New local-model scene accepted: '+theme, flush=True)


def run(force=False):
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
        if not force and status.get('date') == date:
            print('Already attempted today; keeping current scene')
            return
        if not force and datetime.datetime.now().hour >= 6:
            print('Outside generation window; waiting until tonight')
            return
        status = {'date': date, 'success': False, 'attempts': 0}
        status_path.write_text(json.dumps(status))
        theme = THEMES[datetime.date.today().toordinal() % len(THEMES)]
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
                      +design_brief(datetime.date.today())+' '+errors+
                      '\nWrite the function now.<|im_end|>\n<|im_start|>assistant\n')
            (DATA/'prompt.txt').write_text(prompt)
            try:
                command = [str(CLI), '-m', str(MODEL), '-f', str(DATA/'prompt.txt'),
                           '-c', '2048', '-n', '400', '-t', '3', '-b', '64',
                           '--temp', '0.65', '--seed', str(int(time.time()) % 2147483647),
                           '--no-display-prompt']
                generated = run_model(command, seconds)
                if generated.returncode:
                    raise RuntimeError('Model process failed: '+generated.stderr[-800:])
                code = extract_code(generated.stdout)
                activate_scene(code, date, theme, status)
                return
            except (ValueError, SyntaxError, RuntimeError, subprocess.TimeoutExpired) as exc:
                errors = 'Previous attempt failed: '+str(exc)[:300]+'. Simplify the code.'
                status['error'] = str(exc)[:1000]
                status_path.write_text(json.dumps(status, indent=2))
                print('Attempt failed; keeping existing scene: '+str(exc)[:300], flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true')
    run(parser.parse_args().force)
