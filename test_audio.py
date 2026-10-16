import math
import datetime
import unittest
from pathlib import Path

import numpy as np

from scenes import compile_scene
from validate_scene import audio_response
from visualiser import Analysis, BLOCK, RATE
from classic_scenes import classic_scene


class AudioTests(unittest.TestCase):
    def test_classic_fallbacks_respond_to_audio(self):
        for offset in range(4):
            name, code = classic_scene(datetime.date(2026, 10, 16), offset)
            with self.subTest(theme=name):
                self.assertGreater(audio_response(compile_scene(code)), .005)

    def test_recovered_dots_have_a_visible_audio_response(self):
        function = compile_scene(Path('examples/2026-10-15-purple-dots.py').read_text())
        self.assertGreater(audio_response(function), .005)

    def test_room_level_audio_leaves_idle_and_has_visible_level(self):
        state = Analysis(.002)
        wave = np.sin(2*math.pi*440*np.arange(BLOCK)/RATE)
        for i in range(20):
            state.update((wave*.003*math.sqrt(2)*32768).astype(np.int16), 1+i*BLOCK/RATE)
            state.animate(BLOCK/RATE)
        self.assertGreater(state.last_sound, 1)
        self.assertGreater(state.display_level, .35)
        self.assertLessEqual(state.display_level, 1)

    def test_low_noise_does_not_activate_audio(self):
        state = Analysis(.002)
        state.update(np.ones(BLOCK, dtype=np.int16)*10, 1)
        self.assertEqual(state.last_sound, -100)
        self.assertEqual(state.level, 0)

    def test_rain_changes_visibly_at_moderate_audio(self):
        function = compile_scene(Path('reactive_rain.py').read_text())
        self.assertGreater(audio_response(function), .005)

    def test_old_subtle_rain_is_rejected_by_response_metric(self):
        source = '''def draw_frame(draw,t,audio,width,height):
    for i in range(18):
        x = 10+i*320/18
        y = (t*37+i*31)%300
        draw.line((x,y,x,y+5+30*audio['level']), fill=(180,220,240),width=2)
'''
        self.assertLess(audio_response(compile_scene(source)), .005)


if __name__ == '__main__':
    unittest.main()
