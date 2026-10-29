import datetime
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import generate_daily
from classic_series import START, scheduled_scene
from scenes import compile_scene, draw_scene
from validate_scene import audio_response, temporal_response

class SeriesTests(unittest.TestCase):
    def test_dates_and_every_scene(self):
        self.assertEqual(scheduled_scene(START), scheduled_scene(START+datetime.timedelta(days=4)))
        self.assertEqual(scheduled_scene(START+datetime.timedelta(days=3)),
                         scheduled_scene(START+datetime.timedelta(days=403)))
        names = set()
        for offset in range(4):
            name, code = scheduled_scene(START+datetime.timedelta(days=offset))
            names.add(name)
            scene = compile_scene(code)
            self.assertGreater(audio_response(scene), .005)
            self.assertFalse(temporal_response(scene))
            audio = dict(level=.5, bands=(.3,)*24, quiet=True)
            self.assertIsNone(draw_scene(scene, 0, audio).getbbox())
            audio['quiet'] = False
            frame = draw_scene(scene, 0, audio)
            self.assertEqual(set(frame.crop((0,345,360,360)).getdata()), {(8,14,25)})
        self.assertEqual(len(names), 4)

    def test_nightly_series_skips_model_and_records_honest_source(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_daily, 'DATA', Path(folder)):
            with patch('generate_daily.scheduled_scene', return_value=scheduled_scene(START)), patch('generate_daily.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{}', '')) as validator:
                generate_daily.run(force=True)
            status = json.loads((Path(folder)/'generation.json').read_text())
            self.assertEqual(status['source'], 'classic_series')
            self.assertTrue(status['success'])
            self.assertIn('--audio-driven', validator.call_args[0][0])
