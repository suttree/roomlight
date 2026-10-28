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

    def test_runs_at_every_hour(self):
        for hour in range(24):
            with self.subTest(hour=hour):
                self.assertTrue(awake(hour))

    def test_line_endpoints_accept_explicit_colour(self):
        code = '''def draw_frame(draw, t, audio, width, height):
    draw.line((10,10), (10,30), fill=(20,200,80), width=3)
    draw.line((20,10,20,30), (90,100,110), 2)
'''
        image = draw_scene(compile_scene(code), 0, {})
        self.assertEqual(image.getpixel((10,20)), (20,200,80))
        self.assertEqual(image.getpixel((20,20)), (90,100,110))

    def test_acceptance_and_once_per_day(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'current.py').write_text(GOOD)
            with patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')) as validator:
                generate_daily.run(force=True)
                generate_daily.run()
            validator.assert_called_once()
            self.assertIn('--audio-driven', validator.call_args[0][0])
            self.assertIn('PrivateNetwork=yes', validator.call_args[0][0])
            self.assertEqual((data/'previous.py').read_text(), GOOD)
            self.assertEqual((data/'current.py').read_text(),
                             generate_daily.scheduled_scene(datetime.date.today())[1])

    def test_failed_validation_preserves_current_and_can_retry(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'current.py').write_text(GOOD)
            with patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'Rejected')):
                with self.assertRaises(RuntimeError):
                    generate_daily.run()
            self.assertEqual((data/'current.py').read_text(), GOOD)
            self.assertFalse(json.loads((data/'generation.json').read_text())['success'])
            with patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')):
                generate_daily.run()
            self.assertTrue(json.loads((data/'generation.json').read_text())['success'])

    def test_force_same_scene_preserves_previous_backup(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'current.py').write_text(GOOD)
            with patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')):
                generate_daily.run(force=True)
                generate_daily.run(force=True)
            self.assertEqual((data/'previous.py').read_text(), GOOD)

    def test_missing_scene_is_repaired_despite_success_status(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            with patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')) as validator:
                generate_daily.run(force=True)
                (data/'current.py').unlink()
                generate_daily.run()
            self.assertEqual(validator.call_count, 2)
            self.assertTrue((data/'current.py').exists())


if __name__ == '__main__':
    unittest.main()
