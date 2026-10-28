# Roomlight

A microphone-driven display for the Pi 3 and legacy HyperPixel square screen.
Project repository: [suttree/roomlight](https://github.com/suttree/roomlight).
Colourful classic frequency bars and equalisers react to sound. After three seconds below the
noise threshold, the display goes black. It resumes as soon as sound returns. This is an amplitude
and frequency visualiser, not a music beat tracker. No audio is saved or sent.

Requires Python 3, NumPy, Pillow, ALSA's `arecord`, and access to `/dev/fb0`.
On Raspberry Pi OS, install dependencies with:

```sh
sudo apt install python3-numpy python3-pil alsa-utils
```

Run from the Pi's physical console so its prompt doesn't overwrite the image:

```sh
python3 visualiser.py
```

Press Ctrl+C to stop. The previous framebuffer contents are restored.
Use `--noise-floor 0.015` if room noise keeps it active, or a smaller value if
it doesn't respond. `--device` selects
an ALSA capture device. The default uses the USB microphone's card name rather
than its changeable card number. Unplugging the mic shows an error; restart
after reconnecting it.

The installed service uses a 0.002 quiet threshold for this USB microphone.
Audio levels use a decaying peak reference and a square-root curve so normal
room sound produces a visible response. `--stats` also logs RMS input, scaled
level and quiet state, without recording audio. `reactive_rain.py` is the
hand-tuned rain scene with stronger changes in length, width and brightness.

Generate a synthetic-tone preview without Pi hardware:

```sh
python3 visualiser.py --preview preview.png
```

The renderer targets 30 FPS and smooths motion between audio updates. Use
`--fps 20` to lower the target or `--stats` to log the achieved rate every ten
seconds. Common framebuffer formats use Pillow's native encoder; other pixel
layouts retain a generic conversion path.

## On-device classic rotation

Roomlight rotates through four built-in scenes, one per day:

- Full-height rainbow spectrum
- Mirrored rainbow equaliser
- Horizontal rainbow spectrum
- Split rainbow equaliser

Each uses all 24 microphone frequency bands, with no separate volume meter or
bottom divider. The rotation repeats every four days. There is no LLM call,
model runtime, API key or internet connection required. Audio processing and
scene selection happen on the Pi. Both services have network access disabled.

At midnight London time, the display and microphone stop and the backlight
turns off. At 00:10, the daily job selects and validates the next classic.
At 06:00, the display and microphone resume. The Pi stays powered overnight.
Timers follow Europe/London, including daylight saving. A missed nightly job
runs when the Pi next starts.

Before activation, a separate restricted process checks the scene's syntax,
audio response and rendering speed. A failed check leaves the current scene
in place. Accepted scenes are saved in `/var/lib/room-visualiser/history/`,
with the active scene in `current.py` and the last replaced scene in
`previous.py`. The existing `generation.json` filename and systemd unit
names are retained for compatibility. Status reports `source: classic_series`.

Install the Python files and units with `sudo sh install.sh` on the Pi.
Select the first scene and enable the schedule:

```sh
sudo python3 /opt/room-visualiser/generate_daily.py --force
sudo systemctl enable --now room-visualiser-schedule.timer room-visualiser-generate.timer
sudo systemctl start room-visualiser-schedule.service
```

Check status with:

```sh
systemctl list-timers 'room-visualiser*'
journalctl -u room-visualiser.service -n 20
cat /var/lib/room-visualiser/generation.json
```

To revalidate today's classic, run
`sudo python3 /opt/room-visualiser/generate_daily.py --force`.
This is safe during the day and does not require stopping microphone capture.

To disable automatic operation, stop and disable both timers and stop
`room-visualiser.service`. Manual backlight tests use
`sudo python3 /opt/room-visualiser/schedule.py --test off` or `--test on`.

Run `python3 -m unittest discover -v` for rotation, activation, drawing
validation and audio checks. Earlier model grammars and example outputs remain
in the repository as historical fixtures. The installer does not install the
grammars, and the daily job has no model runner or saved-model recovery path.
Existing model downloads are unused and can be removed from the Pi.
