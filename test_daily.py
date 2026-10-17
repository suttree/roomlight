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
    def test_cli_end_marker_is_not_python(self):
        self.assertEqual(generate_daily.extract_code(GOOD+' [end of text]\n'), GOOD)
        self.assertEqual(generate_daily.extract_code('```python\n'+GOOD+'``` [end of text]\n'), GOOD)

    def test_named_function_with_omitted_height_is_normalised(self):
        output = '```python\nimport math\n'+GOOD.replace(
            'draw_frame(draw, t, audio, width, height)',
            'draw_woven_lines(draw, t, audio, width)')+'```\nExplanation.'
        self.assertEqual(generate_daily.extract_code(output), GOOD)

    def test_normalisation_does_not_bypass_restrictions(self):
        invalid = [GOOD.replace('t, audio', 'audio, t'), GOOD+'\n'+GOOD,
                   'def named(draw, t, audio, width):\n    open("/etc/passwd")\n',
                   'def named(draw, t, audio, width=3):\n    pass\n']
        for code in invalid:
            with self.subTest(code=code), self.assertRaises(ValueError):
                generate_daily.extract_code(code)

    def test_saved_output_recovery_uses_validator_without_inference(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'generation.json').write_text(json.dumps({
                'date': datetime.date.today().isoformat(), 'success': False, 'attempts': 2}))
            (data/'last-model-output.txt').write_text(GOOD.replace('draw_frame', 'draw_waves'))
            with patch('generate_daily.run_model') as model, \
                    patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')) as validator:
                generate_daily.run(retry_saved=True)
            model.assert_not_called()
            validator.assert_called_once()
            self.assertEqual((data/'current.py').read_text(), GOOD)
            self.assertTrue(json.loads((data/'generation.json').read_text())['success'])

    def test_saved_recovery_preserves_fallback_when_validation_fails(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            status = {'date': datetime.date.today().isoformat(), 'success': True,
                      'source': 'classic_fallback', 'theme': 'a radial spectrum'}
            (data/'generation.json').write_text(json.dumps(status))
            (data/'current.py').write_text('working fallback')
            (data/'last-model-output.txt').write_text(GOOD+' [end of text]\n')
            with patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'too slow')), self.assertRaises(RuntimeError):
                generate_daily.run(retry_saved=True)
            result = json.loads((data/'generation.json').read_text())
            self.assertTrue(result['success'])
            self.assertEqual(result['source'], 'classic_fallback')
            self.assertEqual((data/'current.py').read_text(), 'working fallback')

    def test_saved_recovery_can_replace_a_classic_fallback(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'generation.json').write_text(json.dumps({
                'date': datetime.date.today().isoformat(), 'success': True, 'source': 'classic_fallback'}))
            (data/'last-model-output.txt').write_text(GOOD+' [end of text]\n')
            with patch('generate_daily.run_model') as model, patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')):
                generate_daily.run(retry_saved=True)
            model.assert_not_called()
            self.assertEqual(json.loads((data/'generation.json').read_text())['source'], 'local_model')

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
            (data/'current.py').write_text('old working scene')
            with patch('generate_daily.run_model', return_value=subprocess.CompletedProcess([], 0, GOOD, '')) as model, \
                    patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"mean_ms": 2}', '')) as run:
                generate_daily.run(force=True)
                self.assertEqual((data/'current.py').read_text(), GOOD)
                self.assertEqual((data/'previous.py').read_text(), 'old working scene')
                generate_daily.run()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(model.call_count, 1)
                command = model.call_args[0][0]
                self.assertIn('--grammar-file', command)
                self.assertTrue((data/'scene.gbnf').exists())

    def test_failed_generation_preserves_previous_scene(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'current.py').write_text(GOOD)
            answer = subprocess.CompletedProcess([], 0, 'not python', '')
            with patch('generate_daily.run_model', return_value=answer), \
                    patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'Rejected')), \
                    self.assertRaises(SystemExit):
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
            with patch('generate_daily.run_model', return_value=answer), \
                    patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'Rejected')), \
                    self.assertRaises(SystemExit):
                generate_daily.run(force=True)
            self.assertEqual((Path(folder)/'current.py').read_text(), GOOD)

    def test_failed_model_activates_classic_and_does_not_repeat_today(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            today = datetime.date.today()
            old_theme, old_code = generate_daily.classic_scene(today)
            (data/'current.py').write_text(old_code)
            (data/'generation.json').write_text(json.dumps({'success': True, 'theme': old_theme}))
            failed = subprocess.CompletedProcess([], 0, 'invalid code', '')
            valid = subprocess.CompletedProcess([], 0, '{}', '')
            with patch('generate_daily.run_model', return_value=failed) as model, \
                    patch('generate_daily.subprocess.run', return_value=valid) as validator:
                generate_daily.run(force=True)
                generate_daily.run()
            status = json.loads((data/'generation.json').read_text())
            self.assertTrue(status['success'])
            self.assertFalse(status['model_success'])
            self.assertEqual(status['source'], 'classic_fallback')
            self.assertIn('No drawing function', status['model_error'])
            self.assertNotEqual(status['theme'], old_theme)
            self.assertEqual((data/'previous.py').read_text(), old_code)
            self.assertEqual(model.call_count, 2)
            validator.assert_called_once()

    def test_failed_day_can_recover_without_more_inference(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            data = Path(folder)
            (data/'generation.json').write_text(json.dumps({
                'date': datetime.date.today().isoformat(), 'success': False, 'error': 'model failed'}))
            with patch('generate_daily.run_model') as model, \
                    patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')):
                generate_daily.run()
            model.assert_not_called()
            self.assertEqual(json.loads((data/'generation.json').read_text())['source'], 'classic_fallback')


if __name__ == '__main__':
    unittest.main()
