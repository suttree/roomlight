import datetime
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_daily
from method_generation import PREFIX, grammar_for_method, layout_signature, matches_method, motion_policy, PALETTES, PAINTS
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

    def test_weekly_policy_keeps_centres_on_straight_paths(self):
        monday = datetime.date(2026, 10, 19)
        for offset in range(7):
            day = monday + datetime.timedelta(days=offset)
            name, x_rule, y_rule = motion_policy(day)
            grammar = grammar_for_method(day)
            self.assertIn('x-coordinate ::= '+x_rule, grammar)
            self.assertIn('y-coordinate ::= '+y_rule, grammar)
            fixed = [rule for rule in (x_rule, y_rule) if rule != 'coordinate']
            self.assertEqual(len(fixed), 0 if offset == 6 else 1)
            if not fixed:
                continue
            expression = json.loads(fixed[0])
            code = METHOD
            if x_rule != 'coordinate':
                code = code.replace('180 + 120 * math.sin(t * 0.3 + i * 0.7)', expression)
            else:
                code = code.replace('180 + 120 * math.cos(t * 0.2 - i * 1.3)', expression)
            self.assertTrue(matches_method(code), name)
            scene = compile_scene(code)
            self.assertGreater(audio_response(scene), .005, name)
            audio = dict(level=.5, bands=(.5,)*24, quiet=False, pulse=0)
            self.assertNotEqual(draw_scene(scene, 0, audio).tobytes(),
                                draw_scene(scene, 2, audio).tobytes(), name)
            audio['quiet'] = True
            self.assertIsNone(draw_scene(scene, 2, audio).getbbox(), name)
            # Fixed coordinates depend only on the shape index, never time/audio.
            for i in range(8):
                positions = {eval(expression, {'__builtins__': {}},
                                  dict(i=i, t=t, energy=energy))
                             for t in (0, 2, 1000) for energy in (0, .2, 1)}
                self.assertEqual(len(positions), 1)
                self.assertTrue(48 <= positions.pop() <= 312)

    def test_expressive_shapes_are_colourful_reactive_and_animate(self):
        for palette in PALETTES:
            self.assertEqual(len(set(palette)), 4)
            for colour in palette:
                self.assertGreater(max(colour)-min(colour), 120)
            for paint in PAINTS:
                code = METHOD.replace('(96, 224, 255)', repr(palette)+'[i % 4]')
                code = code.replace('draw.rectangle((x-r,y-r,x+r,y+r), outline=colour, width=4)', paint)
                self.assertTrue(matches_method(code))
                scene = compile_scene(code)
                self.assertGreater(audio_response(scene), .005, paint)
                audio = dict(level=.5, bands=(.5,)*24, quiet=False, pulse=0)
                first = draw_scene(scene, 0, audio)
                self.assertNotEqual(first.tobytes(), draw_scene(scene, 2, audio).tobytes())
                visible = set(first.getdata()) - {(8, 14, 25)}
                self.assertGreaterEqual(len(visible), 3)
                self.assertTrue(visible.issubset(set(palette)))
                audio['quiet'] = True
                self.assertIsNone(draw_scene(scene, 2, audio).getbbox())

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
