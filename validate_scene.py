"""Run by a separate, restricted systemd process before a scene is activated."""
import hashlib
import json
import math
import resource
import sys
import time
from pathlib import Path

from scenes import compile_scene, draw_scene


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
    silent = {'level': 0., 'bands': (0.,)*24, 'quiet': False, 'pulse': .5}
    loud = {'level': 1., 'bands': (1.,)*24, 'quiet': False, 'pulse': .5}
    if all(draw_scene(function, t, silent).tobytes() == draw_scene(function, t, loud).tobytes()
           for t in (0.3, 1.7, 4.2)):
        raise ValueError('Scene does not react to audio')
    return {'frames': len(elapsed), 'mean_ms': round(mean*1000, 2),
            'distinct_frames': len(pictures)}


if __name__ == '__main__':
    try:
        print(json.dumps(validate(sys.argv[1])))
    except Exception as exc:
        print('Validation failed: '+str(exc), file=sys.stderr)
        sys.exit(1)
