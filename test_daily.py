import datetime
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_daily
from scenes import check_source, compile_scene, draw_scene
from schedule import awake

GOOD = '''def draw_frame(draw, t, audio, width, height):
    x = 180 + 40 * math.sin(t)
    draw.ellipse((x-10, 100, x+10, 120), fill=(40, 200, 180))
'''


class SceneTests(unittest.TestCase):
    def test_rejects_access_outside_drawing_interface(self):
        bad = [
            'import os\n'+GOOD,
            'def draw_frame(draw, t, audio, width, height):\n    open("/etc/passwd")',
            'def draw_frame(draw, t, audio, width, height):\n    x = draw.__class__',
            'def draw_frame(draw, t, audio, width, height):\n    while True: pass',
            'def draw_frame(draw, t, audio, width, height):\n    draw_frame(draw,t,audio,width,height)',
            'def draw_frame(draw, t, audio, width, height):\n    math.sin = 4',
        ]
        for code in bad:
            with self.subTest(code=code), self.assertRaises(ValueError):
                check_source(code)

    def test_valid_scene_animates(self):
        scene = compile_scene(GOOD)
        self.assertNotEqual(draw_scene(scene, 0, {}).tobytes(), draw_scene(scene, 1, {}).tobytes())

    def test_bounds_drawing_work(self):
        code = 'def draw_frame(draw, t, audio, width, height):\n    for i in range(100000):\n        pass'
        with self.assertRaises(ValueError):
            draw_scene(compile_scene(code), 0, {})

    def test_separate_endpoints_and_point_dots(self):
        code = '''def draw_frame(draw, t, audio, width, height):
    draw.line((10, 10), (10, 30), width=2)
    draw.ellipse((50, 50), fill=(200, 100, 50))
'''
        image = draw_scene(compile_scene(code), 0, {})
        self.assertEqual(image.getpixel((10, 20)), (180, 220, 240))
        self.assertEqual(image.getpixel((50, 50)), (200, 100, 50))

    def test_quiet_hours(self):
        self.assertFalse(awake(0))
        self.assertFalse(awake(5))
        self.assertTrue(awake(6))
        self.assertTrue(awake(23))

    def test_acceptance_and_once_per_day(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'current.py').write_text('old working scene')
            with patch('generate_daily.run_model', return_value=subprocess.CompletedProcess([], 0, GOOD, '')) as model, \
                    patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"mean_ms": 2}', '')) as run:
                generate_daily.run(force=True)
                self.assertEqual((data/'current.py').read_text(), GOOD)
                self.assertEqual((data/'previous.py').read_text(), 'old working scene')
                generate_daily.run()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(model.call_count, 1)

    def test_failed_generation_preserves_previous_scene(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'current.py').write_text(GOOD)
            answer = subprocess.CompletedProcess([], 0, 'not python', '')
            with patch('generate_daily.run_model', return_value=answer), self.assertRaises(SystemExit):
                generate_daily.run(force=True)
            self.assertEqual((data/'current.py').read_text(), GOOD)
            self.assertFalse(json.loads((data/'generation.json').read_text())['success'])

    def test_incomplete_code_is_retried(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            answers = [subprocess.CompletedProcess([], 0, 'def draw_frame(', ''),
                       subprocess.CompletedProcess([], 0, GOOD, '')]
            with patch('generate_daily.run_model', side_effect=answers), \
                    patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"mean_ms": 2}', '')):
                generate_daily.run(force=True)
            status = json.loads((Path(folder)/'generation.json').read_text())
            self.assertTrue(status['success'])
            self.assertEqual(status['attempts'], 2)

    def test_identical_scene_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            (Path(folder)/'current.py').write_text(GOOD)
            answer = subprocess.CompletedProcess([], 0, GOOD, '')
            with patch('generate_daily.run_model', return_value=answer), self.assertRaises(SystemExit):
                generate_daily.run(force=True)
            self.assertEqual((Path(folder)/'current.py').read_text(), GOOD)


if __name__ == '__main__':
    unittest.main()
