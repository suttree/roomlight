import unittest
from pathlib import Path
from scenes import compile_scene, draw_scene
from validate_scene import audio_response, temporal_response

class SpectrumTests(unittest.TestCase):
    def test_frequency_bands_are_independent_and_silence_is_black(self):
        scene = compile_scene(Path('examples/2026-10-25-rainbow-spectrum.py').read_text())
        self.assertGreater(audio_response(scene), .005)
        self.assertFalse(temporal_response(scene))
        for index in (0, 11, 23):
            bands = [0.0]*24
            bands[index] = .8
            audio = dict(level=.5, bands=bands, quiet=False)
            frame = draw_scene(scene, 0, audio)
            for i in range(24):
                self.assertEqual(frame.getpixel((18+i*14, 200)) != (8,14,25), i == index)
            audio['quiet'] = True
            self.assertIsNone(draw_scene(scene, 0, audio).getbbox())
