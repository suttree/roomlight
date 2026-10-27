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

## Daily local generation

The installed version uses Qwen2.5-Coder-0.5B-Instruct, quantised to Q4_K_M,
through llama.cpp b3889. Inference runs entirely on the Pi. It receives a drawing
prompt, date and theme, without microphone recordings or transcripts.
Generation uses a Python grammar that keeps the function signature, eight-shape
loop and audio-energy definitions intact. The model writes the x and y position
expressions, combines time and shape index with arithmetic, sine, cosine or
modulo, and chooses colours, angle formulas and drawing primitives. Position
expressions include a required shape-index offset to reduce accidental overlap.
Every day, one position axis stays fixed, alternating vertical paths, horizontal
paths, columns and rows. This prevents orbiting layouts, including on Sundays.
The model still
writes the moving-axis formula and chooses shapes, angles and colours. The
selected rule is recorded as `motion_policy` in the generation status. It can use
sweeping arcs, flowing sine ribbons and rotating shards. Chevrons are excluded.
Moving coordinates and angles include time, and validation checks movement with
audio held constant so audio-only size changes cannot pass as animation.
Saturated four-colour palettes cycle across the shapes; neutral colours and
plain boxes are excluded from new model outputs.

These expressions compose new layouts rather than selecting one of sixteen
finished scene bodies. The grammar still limits the available Python language,
coordinates, shape count and drawing APIs to suit the Pi. Theme names are prompt
inspiration, not a guarantee of what the resulting scene depicts.
`generation_format: procedural_python_v2` identifies these runs. A structural
comparison rejects the immediately previous procedural layout when only its
numbers or colour have changed. This is a code comparison, not a visual novelty
score, so distinct formulas can still produce similar-looking results.

The previous `constrained_python_v1` mode only varied parameters within fixed
compositions. Its fixtures remain for regression tests and saved-output recovery.

The rotation includes classic spectrum bars, a mirrored equaliser, a radial
spectrum and an oscilloscope-style wave. The spectrum styles use 24 microphone
frequency bands, grouped into 8 to 12 shapes. The wave is a sine animation driven
by audio level, not a trace of raw microphone samples. Every scene goes black when the room is quiet and must pass the usual validation
before activation. The microphone keeps listening so sound wakes the display.

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
the original bars and circle. Drawing runs under the `visdisplay` system account
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

Run `python3 -m unittest -v test_daily test_audio test_constrained test_method_generation` for audio sensitivity, scheduler, validation and rollback
checks. `example_scene.py` is a handwritten test fixture, not generated output.

`examples/2026-10-17-constrained-flower.py` is the actual constrained model output
from the Pi trial, accepted after fixing CLI marker handling, without manual
changes to the drawing code.

`examples/2026-10-18-procedural-orbits.py` is an unedited model-generated method
from the procedural trial. It draws grey rings whose positions and sizes respond
to audio. After adding the index-spacing rule, the trial passed on its first
attempt, with 8.81 ms mean drawing time and 2.38% changed pixels in the audio test.

The `examples/2026-10-25-rainbow-spectrum.py` scene is a handwritten classic
spectrum: 24 independently driven frequency bars, rainbow colours, white caps,
and a separate volume meter. It has no time-driven motion. Manual activation
with `source: manual` and `animation_mode: audio_driven` uses the validator's
`--audio-driven` option, retaining syntax, performance and audio-response checks
without requiring motion under constant audio. Nightly model scenes still
require time-driven motion.

The nightly job permanently rotates through four tested classic scenes:
full-height rainbow bars, a mirrored equaliser, horizontal spectrum bars and a
split equaliser. These are curated scenes (`source: classic_series`), not LLM
outputs. Each uses all 24 frequency bands. There is no separate volume meter or
bottom divider. A square-root response makes quieter bands more visible;
quiet blanking is unchanged. The rotation repeats every four days and does not
return to procedural model generation. The older model code and examples remain
available for reference.
