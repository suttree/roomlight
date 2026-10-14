# Room visualiser prototype

A microphone-driven display for the Pi 3 and legacy HyperPixel square screen.
Frequency bars and a circle react to sound. After three seconds below the
noise threshold, the circle pulses silently at 72 BPM. This is an amplitude
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
it doesn't respond. `--bpm 90` changes the quiet pulse rate. `--device` selects
an ALSA capture device. The default uses the USB microphone's card name rather
than its changeable card number. Unplugging the mic shows an error; restart
after reconnecting it.

Generate a synthetic-tone preview without Pi hardware:

```sh
python3 visualiser.py --preview preview.png
```

The renderer targets 30 FPS and smooths motion between audio updates. Use
`--fps 20` to lower the target or `--stats` to log the achieved rate every ten
seconds. Common framebuffer formats use Pillow's native encoder; other pixel
layouts retain a generic conversion path.

This is a manual test application. It doesn't change boot settings or autostart.
