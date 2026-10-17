# Room visualiser

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

## Daily local generation

The installed version uses Qwen2.5-Coder-0.5B-Instruct, quantised to Q4_K_M,
through llama.cpp b3889. Inference runs entirely on the Pi. It receives a drawing
prompt, date and theme, without microphone recordings or transcripts.
Generation uses a llama.cpp grammar with sixteen tested Python scene structures.
The model emits the complete drawing function, choosing from bounded motion
speeds, phase offsets, audio gains and daily colour palettes. The grammar fixes
variable definitions, the eight-shape loop and drawing calls. It cannot omit
`strength`, use an undefined `i` or add another drawing loop.

This is deliberately constrained variation within handwritten compositions,
not freeform code invention. The previous prompt-only approach repeatedly
produced invalid code on the 0.5B model. The output must also match the selected
structure before the normal isolated rendering and audio checks run.
`generation_format: constrained_python_v1` identifies these runs in the status.

The rotation includes classic spectrum bars, a mirrored equaliser, a radial
spectrum and an oscilloscope-style wave. The spectrum styles use 24 microphone
frequency bands, grouped into 8 to 12 shapes. The wave is a sine animation driven
by audio level, not a trace of raw microphone samples. All four use the silent
pulse when the room is quiet and must pass the usual validation before activation.

At 00:00 London time the service stops microphone capture and turns off the
HyperPixel backlight. At 00:10 the model gets up to two attempts to write a short
Python drawing function. At 06:00 the screen and microphone resume. The Pi stays
powered overnight. Timers follow Europe/London, including daylight saving.

Generated code uses a restricted drawing interface. A separate process tests
animation, audio response and rendering speed before replacing the current
scene. After both model attempts fail, a handwritten classic theme goes through the same
validation and replaces the previous scene. The four classic styles rotate by
date, vary their colour and avoid the previous accepted theme. If a classic fails
validation, the next is tried. Only failure of every candidate keeps the old scene. Runtime errors fall back to
the original bars and pulse. Drawing runs under the `visdisplay` system account
with no network access and a read-only system filesystem. This combines syntax
restrictions with OS process isolation; Python syntax checks alone are not a
security boundary.
The audio check compares silence with a moderate level of 0.2. At least 0.5%
of screen pixels must change by 12 colour values or more, averaged over three
frames, so a barely visible response cannot pass on pixel inequality alone.
The interface accepts Pillow-style calls, plus separate endpoints for a line
with an optional explicit colour, and a single centre point for a small dot,
to tolerate common small-model output.
The loader also accepts a single named drawing function using the expected
arguments, with an optional omitted `height` argument. It normalises only the
function header, then runs the same syntax, audio and rendering checks.

The model is small, so some nights may produce rejected code. A successful
fallback records `source: classic_fallback`, `model_success: false`, and the last
model error in `generation.json`; it is not reported as an LLM success. Each date gets one
generation job, with two attempts. Accepted scripts are saved in
`/var/lib/room-visualiser/history/`, including accepted classics, with the active script at `current.py` and
the last replaced script at `previous.py`. `generation.json` records results.
Each model attempt has a 45-minute limit and is stopped by 06:00 for scheduled
runs. `last-model-output.txt` and `last-model-stderr.txt` show live progress.

Install the Python files and units with `sudo sh install.sh` on the Pi, then put
the executable and model at `/opt/room-visualiser-model/llama-cli` and
`/opt/room-visualiser-model/qwen-coder.gguf` respectively. Enable after testing:

```sh
sudo systemctl enable --now room-visualiser-schedule.timer room-visualiser-generate.timer
sudo systemctl start room-visualiser-schedule.service
```

The display service itself is controlled by the schedule. Check status with:

```sh
systemctl list-timers 'room-visualiser*'
journalctl -u room-visualiser.service -n 20
cat /var/lib/room-visualiser/generation.json
```

After fixing a compatibility problem, revalidate today's failed model output
without another inference run with
`sudo python3 /opt/room-visualiser/generate_daily.py --retry-saved`.
It only accepts output from today's job and still requires validation. It can
replace an active classic fallback after a parser fix, but preserves the fallback
if validation fails. The llama.cpp end-of-generation marker is stripped before
parsing; generated Python is otherwise unchanged.

To test generation during the day, stop the schedule timer and display first
so the model has the Pi's memory and CPU, then restore the schedule:

```sh
sudo systemctl stop room-visualiser-schedule.timer
sudo python3 /opt/room-visualiser/schedule.py --test off
sudo python3 /opt/room-visualiser/generate_daily.py --force
sudo systemctl start room-visualiser-schedule.timer room-visualiser-schedule.service
```

To disable automatic operation, stop and disable both timers and stop
`room-visualiser.service`. Manual backlight tests use
`sudo python3 /opt/room-visualiser/schedule.py --test off` or `--test on`.

Model source: [official Qwen GGUF repository](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF).
The downloaded Q4_K_M file has SHA256
`1d9614638d18024d0fbb36575a15f1302a3adf044df10345688ec4f6e1c4ff32`.
Runtime source: [llama.cpp b3889](https://github.com/ggml-org/llama.cpp/tree/b3889),
built on the 32-bit Buster Pi with `make -j2 llama-cli`.

Run `python3 -m unittest -v test_daily test_audio test_constrained` for audio sensitivity, scheduler, validation and rollback
checks. `example_scene.py` is a handwritten test fixture, not generated output.

`examples/2026-10-17-constrained-flower.py` is the actual constrained model output
from the Pi trial, accepted after fixing CLI marker handling, without manual
changes to the drawing code.
