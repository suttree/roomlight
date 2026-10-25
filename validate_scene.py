"""Run by a separate, restricted systemd process before a scene is activated."""
import hashlib
import json
import math
import resource
import sys
import time
from pathlib import Path
from PIL import ImageChops

from scenes import compile_scene, draw_scene


def audio_response(function):
    silent = {'level': 0., 'bands': (0.,)*24, 'quiet': False, 'pulse': .5}
    moderate = {'level': .2, 'bands': (.2,)*24, 'quiet': False, 'pulse': .5}
    fractions = []
    for t in (.3, 1.7, 4.2):
        before = draw_scene(function, t, silent)
        after = draw_scene(function, t, moderate)
        channels = ImageChops.difference(before, after).split()
        difference = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        fractions.append(sum(difference.histogram()[12:]) / (360*360))
    return sum(fractions)/len(fractions)


def temporal_response(function):
    audio = {'level': .5, 'bands': (.5,)*24, 'quiet': False, 'pulse': .5}
    frames = [draw_scene(function, t, audio) for t in (0., .7, 1.9)]
    return any(ImageChops.difference(frames[0], frame).getbbox() for frame in frames[1:])


def validate(path):
    resource.setrlimit(resource.RLIMIT_AS, (192*1024*1024, 192*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    source = Path(path).read_text()
    function = compile_scene(source)
    elapsed = []
    pictures = set()
    for i in range(100):
        t = i*.173 + (1000000 if i >= 75 else 0)
        level = (0, .05, .4, 1.0)[(i//25) % 4]
        audio = {'level': level, 'bands': tuple(level*(.5+.5*math.sin(t+j)) for j in range(24)),
                 'quiet': i < 25, 'pulse': .5+.5*math.sin(t*7)}
        start = time.monotonic()
        image = draw_scene(function, t, audio, budget=.08)
        elapsed.append(time.monotonic()-start)
        pictures.add(hashlib.sha256(image.tobytes()).hexdigest())
    mean = sum(elapsed)/len(elapsed)
    if mean > .015:
        raise ValueError('Scene drawing too slow: %.1f ms' % (mean*1000))
    if len(pictures) < 3:
        raise ValueError('Scene does not animate')
    if not temporal_response(function):
        raise ValueError('Scene does not move with constant audio. Use time in visible positions or drawing angles.')
    response = audio_response(function)
    if response < .005:
        raise ValueError('Audio response too subtle at level 0.2. Make size and brightness change much more.')
    return {'frames': len(elapsed), 'mean_ms': round(mean*1000, 2),
            'distinct_frames': len(pictures), 'audio_changed_percent': round(response*100, 2)}


if __name__ == '__main__':
    try:
        print(json.dumps(validate(sys.argv[1])))
    except Exception as exc:
        print('Validation failed: '+str(exc), file=sys.stderr)
        sys.exit(1)
