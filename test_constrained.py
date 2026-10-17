import datetime
import unittest

from constrained_scene import grammar_for, matches_spec, scene_spec
from scenes import compile_scene, draw_scene
from validate_scene import audio_response


def sample(day, choice):
    _, template, options = scene_spec(day)
    for key, values in options.items():
        template = template.replace('@'+key+'@', values[choice])
    return template


class ConstrainedTests(unittest.TestCase):
    def test_all_structures_animate_and_respond_at_parameter_extremes(self):
        start = datetime.date(2026, 10, 17)
        for offset in range(16):
            day = start+datetime.timedelta(days=offset)
            for choice in range(3):
                with self.subTest(day=day, choice=choice):
                    code = sample(day, choice)
                    self.assertTrue(matches_spec(code, day))
                    scene = compile_scene(code)
                    self.assertGreater(audio_response(scene), .005)
                    for quiet in (False, True):
                        audio = dict(level=1., bands=(1.,)*24, quiet=quiet, pulse=.7)
                        pictures = {draw_scene(scene, t, audio).tobytes()
                                    for t in (.3, 1.7, 4.2, 1000000.7)}
                        if quiet:
                            self.assertEqual(pictures, {bytes(360*360*3)})
                        else:
                            self.assertGreater(len(pictures), 1)


    def test_missing_definitions_and_unbounded_values_are_rejected(self):
        day = datetime.date(2026, 10, 17)
        code = sample(day, 0)
        for invalid in (code.replace('for i in range(8):', 'for j in range(8):'),
                        code.replace('0.6 + 0.0', '999999 + 0.0'),
                        code.replace("audio['level']", "audio['strength']"), code[:100]):
            self.assertFalse(matches_spec(invalid, day))

    def test_grammar_has_no_unresolved_markers(self):
        for offset in range(16):
            _, grammar = grammar_for(datetime.date(2026, 10, 17)+datetime.timedelta(days=offset))
            self.assertNotIn('@', grammar)
            self.assertTrue(grammar.startswith('root ::= '))


if __name__ == '__main__':
    unittest.main()
