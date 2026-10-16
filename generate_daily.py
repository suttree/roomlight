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
from classic_scenes import classic_scene, NAMES as CLASSIC_NAMES

BASE = Path('/opt/room-visualiser')
DATA = Path('/var/lib/room-visualiser')
MODEL = Path('/opt/room-visualiser-model/qwen-coder.gguf')
CLI = Path('/opt/room-visualiser-model/llama-cli')

INSTRUCTIONS = '''Write a tiny animated Python drawing function. Output code only, no comments.
Use the exact function signature shown below. Keep the whole function under 12 lines.
The canvas is 360 by 360. t is time in seconds. audio['level'] and audio['pulse']
are numbers between 0 and 1. audio['quiet'] is a bool. Use pulse when quiet.
audio['bands'] contains 24 frequency levels from bass to treble, each from 0 to 1.
Only use math.sin, math.cos, math.pi, range, int, min, max and draw.line or draw.ellipse.
No imports or other functions. RGB colours must be integer tuples from 0 to 255.
Use at most 12 shapes. Keep all coordinates within the screen.
Audio must visibly change size and brightness, even at level 0.2. Use large
changes such as size=8+100*strength and colour components=50+200*strength.
Start with: def draw_frame(draw, t, audio, width, height):
Then set strength = audio['pulse'] if audio['quiet'] else audio['level'].
Use exactly ONE for loop and ONE drawing call inside it. Draw only the requested
design. Do not add a background or another composition.
For a line use draw.line((x1,y1,x2,y2), fill=(r,g,b), width=4).
For a circle outline use draw.ellipse((x-r,y-r,x+r,y+r), outline=(r,g,b), width=2).
For a filled dot use draw.ellipse((x-r,y-r,x+r,y+r), fill=(r,g,b)).
Use one coordinate tuple. Put colour and stroke width in the drawing call.
'''
THEMES = ['orbiting moons', 'sound ripples', 'a geometric flower',
          'a constellation', 'waves', 'a spiral of dots',
          'rotating spokes', 'falling rain', 'woven lines',
          'a slowly breathing sun', 'dancing columns', 'radial sparks',
          'classic spectrum bars', 'a mirrored equaliser',
          'a radial spectrum', 'an oscilloscope-style wave']


def design_brief(day):
    """Give the tiny model concrete geometry, varying it deterministically each day."""
    seed = day.toordinal()
    count = 8 + seed % 5
    speed = 20 + seed % 41
    colour = tuple(int(c*255) for c in colorsys.hsv_to_rgb((seed*.61803398875) % 1, .65, 1))
    forms = [
        'Draw orbiting dots. angle=i*2*math.pi/N+t*0.3; radius=55+i*4+20*strength. '
        'Place dots at (180+radius*math.cos(angle),180+radius*math.sin(angle)), size 6+25*strength.',
        'Draw expanding circle outlines centred at (180,180). '
        'radius=10+(i*13+t*SPEED)%110+30*strength. Use outline=COLOUR and width=2, no fill.',
        'Draw a radial flower of lines from (180,180). angle=i*2*math.pi/N+t*0.15. '
        'radius=60+60*strength+25*math.sin(t+i). End at (180+radius*math.cos(angle),180+radius*math.sin(angle)).',
        'Draw dots at x=20+(i*43)%320, y=180+100*math.sin(t*0.5+i*0.7). Size 6+25*strength.',
        'Draw short horizontal wave lines. x=10+i*320/N; y=180+70*math.sin(t+i*0.5). '
        'Draw from (x,y) to (x+8,y+100*strength), width=4.',
        'Draw spiral dots. angle=i*0.65+t*0.3; radius=10+i*5. '
        'Place dots at (180+radius*math.cos(angle),180+radius*math.sin(angle)), size 6+25*strength.',
        'Draw rotating spokes. angle=i*2*math.pi/N-t*0.4. '
        'Draw from (180+40*math.cos(angle),180+40*math.sin(angle)) '
        'to (180+(55+100*strength)*math.cos(angle),180+(55+100*strength)*math.sin(angle)), width=4.',
        'Replace the example with falling rain. Use vertical lines, not circles. '
        'For each i, x=10+i*320/N; y=(t*SPEED+i*31)%220. '
        'Draw from (x,y) to (x,y+8+115*strength), width=3. Remove angle, sin and cos.',
        'Draw woven lines. y=15+i*320/N. '
        'Draw from (20,y) to (340,180+120*math.sin(t*0.4+i*0.25)*(.3+strength*.7)), width=2.',
        'Draw concentric breathing circle outlines at (180,180). '
        'radius=10+i*5+15*strength+5*math.sin(t). Use outline=COLOUR, width=2, no fill.',
        'Draw vertical sound columns as thick lines. x=15+i*320/N; '
        'h=10+140*strength*(.5+.5*math.sin(t+i)). Draw from (x,300) to (x,300-h), width=6.',
        'Draw radial sparks as short lines. angle=i*2*math.pi/N; radius=20+(t*SPEED+i*9)%70. '
        'Draw from (180+radius*math.cos(angle),180+radius*math.sin(angle)) '
        'to (180+(radius+5+70*strength)*math.cos(angle),180+(radius+5+70*strength)*math.sin(angle)), width=6.',
        'Draw classic spectrum bars as thick vertical lines. '
        "energy=strength if audio['quiet'] else min(1,0.4*strength+0.6*audio['bands'][int(i*24/N)]). "
        'x=25+i*310/N; h=12+220*energy+4*math.sin(t*2+i). '
        'Draw from (x,320) to (x,320-h), width=12.',
        'Draw a classic mirrored equaliser across the horizontal centre. '
        "energy=strength if audio['quiet'] else min(1,0.4*strength+0.6*audio['bands'][int(i*24/N)]). "
        'x=25+i*310/N; h=8+140*energy+3*math.sin(t*2+i). '
        'Draw one vertical line from (x,180-h) to (x,180+h), width=10.',
        'Draw a classic radial spectrum of thick spokes around an empty centre. '
        "energy=strength if audio['quiet'] else min(1,0.4*strength+0.6*audio['bands'][int(i*24/N)]). "
        'angle=i*2*math.pi/N+t*0.15; r=65+95*energy. '
        'Draw from (180+45*math.cos(angle),180+45*math.sin(angle)) '
        'to (180+r*math.cos(angle),180+r*math.sin(angle)), width=10.',
        'Draw a connected oscilloscope-style sine wave using N line segments. '
        'This is an audio-level animation, not raw microphone samples. '
        'amplitude=12+135*strength; x=20+i*320/N; next_x=20+(i+1)*320/N. '
        'y=180+amplitude*math.sin(i*4*math.pi/N+t*2); '
        'next_y=180+amplitude*math.sin((i+1)*4*math.pi/N+t*2). '
        'Draw from (x,y) to (next_x,next_y), width=6.'
    ]
    return (forms[seed % len(forms)]
            .replace('N', str(count)).replace('SPEED', str(speed)).replace('COLOUR', str(colour))
            + ' Use for i in range('+str(count)+') and RGB colour '+str(colour)
            + '. Keep the strength line. Output only the rewritten function.')


def extract_code(text):
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
            if status.get('success'):
                print('Today already has an accepted scene')
                return
            code = extract_code((DATA/'last-model-output.txt').read_text())
            status['recovered_from_saved_output'] = True
            status['source'] = 'local_model'
            status.pop('model_success', None)
            theme = THEMES[datetime.date.today().toordinal() % len(THEMES)]
            try:
                activate_scene(code, date, theme, status)
            except (ValueError, SyntaxError, RuntimeError, subprocess.TimeoutExpired) as exc:
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
                  'previous_theme': previous_theme, 'source': 'local_model'}
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
