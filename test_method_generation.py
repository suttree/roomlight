import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_daily
from method_generation import PREFIX, grammar_for_method, layout_signature, matches_method
from scenes import compile_scene, draw_scene
from validate_scene import audio_response

METHOD = PREFIX+'''        x = 180 + 120 * math.sin(t * 0.3 + i * 0.7)
        y = 180 + 120 * math.cos(t * 0.2 - i * 1.3)
        r = 8 + 40 * energy
        angle = t + i
        colour = (96, 224, 255)
        draw.rectangle((x-r,y-r,x+r,y+r), outline=colour, width=4)
'''


class MethodTests(unittest.TestCase):
    def test_new_layout_has_audio_response_animation_and_quiet_blanking(self):
        self.assertTrue(matches_method(METHOD))
        scene = compile_scene(METHOD)
        self.assertGreater(audio_response(scene), .005)
        audio = dict(level=.5, bands=(.5,)*24, quiet=False, pulse=0)
        pictures = {draw_scene(scene, t, audio).tobytes() for t in (0, 1, 1000000)}
        self.assertEqual(len(pictures), 3)
        audio['quiet'] = True
        self.assertIsNone(draw_scene(scene, 3, audio).getbbox())

    def test_undefined_variables_or_missing_definitions_are_rejected(self):
        for code in (METHOD.replace('angle = t + i', 'angle = t + missing'),
                     METHOD.replace('x = 180', 'x = x'),
                     METHOD.replace('for i in range(8)', 'for j in range(8)'),
                     METHOD.replace('        angle = t + i\n', ''), METHOD[:-50]):
            self.assertFalse(matches_method(code))

    def test_numeric_and_palette_changes_do_not_count_as_new_layout(self):
        retuned = METHOD.replace('0.3', '0.9').replace('(96, 224, 255)', '(255, 64, 96)')
        changed = METHOD.replace('math.sin(t * 0.3 + i * 0.7)', 'math.cos(t * 0.3 - i * 0.7)')
        self.assertEqual(layout_signature(METHOD), layout_signature(retuned))
        self.assertNotEqual(layout_signature(METHOD), layout_signature(changed))
        with tempfile.TemporaryDirectory() as directory, patch.object(generate_daily, 'DATA', Path(directory)):
            (Path(directory)/'current.py').write_text(METHOD)
            with self.assertRaisesRegex(ValueError, 'repeats the previous layout'):
                generate_daily.activate_scene(retuned, '2026-10-18', 'test', {
                    'source': 'local_model', 'generation_format': 'procedural_python_v2'})

    def test_model_command_uses_procedural_grammar(self):
        grammar = grammar_for_method()
        self.assertIn('expression ::=', grammar)
        self.assertIn('paint ::=', grammar)
        self.assertIn('draw.polygon', grammar)
        self.assertNotIn('@', grammar)
        with tempfile.TemporaryDirectory() as directory, patch.object(generate_daily, 'DATA', Path(directory)):
            with patch('generate_daily.run_model', return_value=subprocess.CompletedProcess([], 0, METHOD, '')) as model, patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')):
                generate_daily.run(force=True)
            status = json.loads((Path(directory)/'generation.json').read_text())
            self.assertEqual(status['generation_format'], 'procedural_python_v2')
            self.assertEqual((Path(directory)/'scene.gbnf').read_text(), grammar)
            self.assertIn('--grammar-file', model.call_args[0][0])


if __name__ == '__main__':
    unittest.main()
