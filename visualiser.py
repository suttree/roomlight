#!/usr/bin/env python3
"""Room audio visualiser for a Linux framebuffer. Audio stays in memory."""
import argparse
import ctypes
import fcntl
import math
import mmap
import os
import select
import signal
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

RATE, BLOCK, SIZE = 16000, 1024, 360
FONT = ImageFont.load_default()


class FixedInfo(ctypes.Structure):
    _fields_ = [('id', ctypes.c_char * 16), ('smem_start', ctypes.c_ulong),
                ('smem_len', ctypes.c_uint32), ('type', ctypes.c_uint32),
                ('type_aux', ctypes.c_uint32), ('visual', ctypes.c_uint32),
                ('xpanstep', ctypes.c_uint16), ('ypanstep', ctypes.c_uint16),
                ('ywrapstep', ctypes.c_uint16), ('line_length', ctypes.c_uint32),
                ('mmio_start', ctypes.c_ulong), ('mmio_len', ctypes.c_uint32),
                ('accel', ctypes.c_uint32), ('capabilities', ctypes.c_uint16),
                ('reserved', ctypes.c_uint16 * 2)]


class Framebuffer:
    def __init__(self, path):
        self.file = open(path, 'r+b', buffering=0)
        var = bytearray(160)
        fcntl.ioctl(self.file, 0x4600, var, True)
        v = np.frombuffer(var, dtype=np.uint32)
        self.width, self.height = int(v[0]), int(v[1])
        self.xoff, self.yoff, self.bits = int(v[4]), int(v[5]), int(v[6])
        self.channels = [(int(v[i]), int(v[i+1])) for i in (8, 11, 14)]
        self.raw_mode = {
            (32, ((16, 8), (8, 8), (0, 8))): 'BGRX',
            (32, ((0, 8), (8, 8), (16, 8))): 'RGBX',
            (24, ((16, 8), (8, 8), (0, 8))): 'BGR',
            (24, ((0, 8), (8, 8), (16, 8))): 'RGB',
        }.get((self.bits, tuple(self.channels)))
        if self.bits not in (16, 24, 32) or any(int(v[i]) for i in (10, 13, 16)):
            raise RuntimeError('Unsupported framebuffer pixel format')
        fixed = bytearray(ctypes.sizeof(FixedInfo))
        fcntl.ioctl(self.file, 0x4602, fixed, True)
        info = FixedInfo.from_buffer_copy(fixed)
        self.stride = info.line_length
        self.memory = mmap.mmap(self.file.fileno(), info.smem_len)
        self.bytewidth = self.width * (self.bits // 8)
        self.offset = self.yoff * self.stride + self.xoff * (self.bits // 8)
        self.original = [self.memory[self.offset+y*self.stride:self.offset+y*self.stride+self.bytewidth]
                         for y in range(self.height)]

    def show(self, picture):
        picture = picture.resize((self.width, self.height), Image.NEAREST)
        if self.raw_mode:
            pixels = picture.tobytes('raw', self.raw_mode)
            if self.stride == self.bytewidth:
                self.memory[self.offset:self.offset+len(pixels)] = pixels
            else:
                for y in range(self.height):
                    start = self.offset+y*self.stride
                    self.memory[start:start+self.bytewidth] = pixels[y*self.bytewidth:(y+1)*self.bytewidth]
            return
        rgb = np.asarray(picture, dtype=np.uint32)
        packed = np.zeros(rgb.shape[:2], dtype=np.uint32)
        for index, (offset, length) in enumerate(self.channels):
            packed |= ((rgb[:, :, index] * ((1 << length)-1) // 255) << offset)
        if self.bits == 16:
            rows = packed.astype('<u2').view(np.uint8).reshape(self.height, -1)
        else:
            rows = packed.astype('<u4').view(np.uint8).reshape(self.height, self.width, 4)
            rows = np.ascontiguousarray(rows[:, :, :self.bits//8]).reshape(self.height, -1)
        for y, row in enumerate(rows):
            start = self.offset + y*self.stride
            self.memory[start:start+self.bytewidth] = row.tobytes()

    def close(self):
        for y, row in enumerate(self.original):
            start = self.offset + y*self.stride
            self.memory[start:start+self.bytewidth] = row
        self.memory.close()
        self.file.close()


class Analysis:
    def __init__(self, floor):
        self.floor = floor
        self.bars = np.zeros(24)
        self.level = 0.0
        self.rms = 0.0
        self.peak_rms = max(floor*5, .008)
        self.display_bars = np.zeros(24)
        self.display_level = 0.0
        self.last_sound = -100.0
        self.window = np.hanning(BLOCK)
        freq = np.fft.rfftfreq(BLOCK, 1/RATE)
        edges = np.geomspace(70, 7500, 25)
        self.bins = [(freq >= low) & (freq < high) for low, high in zip(edges, edges[1:])]

    def update(self, samples, now):
        samples = samples.astype(float) / 32768
        samples -= samples.mean()
        rms = float(np.sqrt(np.mean(samples**2)))
        self.rms = rms
        if rms > self.floor:
            self.last_sound = now
        # Follow louder material, then release over several seconds. A fixed
        # minimum reference prevents silence from acquiring unlimited gain.
        self.peak_rms = max(rms, self.peak_rms * math.exp(-(len(samples)/RATE)/8))
        reference = max(self.floor*5, .008, self.peak_rms)
        target_level = math.sqrt(min(1, max(0, rms-self.floor*.5)/reference))
        self.level = .45*self.level + .55*target_level
        spectrum = np.abs(np.fft.rfft(samples*self.window)) / (BLOCK/2)
        target = np.array([np.max(spectrum[b]) if b.any() else 0 for b in self.bins])
        target = np.clip((20*np.log10(target+1e-8)+65)/55, 0, 1)
        self.bars = np.maximum(target, self.bars*.8)

    def animate(self, elapsed):
        blend = 1-math.exp(-max(0, elapsed)/.06)
        self.display_bars += (self.bars-self.display_bars)*blend
        self.display_level += (self.level-self.display_level)*blend


def render(state, now, bpm, error=False):
    quiet = now-state.last_sound > 3
    pulse = math.exp(-((now*bpm/60) % 1)*5) if quiet else state.display_level
    image = Image.new('RGB', (SIZE, SIZE), '#080e19')
    draw = ImageDraw.Draw(image)
    colour = (90, 148, 230) if quiet else (62, 224, 185)
    radius = 48 + int(22*pulse)
    for extra, shade in ((16, .15), (8, .3), (0, 1)):
        r = radius+extra
        draw.ellipse((180-r, 139-r, 180+r, 139+r), outline=tuple(int(c*shade) for c in colour), width=2)
    draw.ellipse((174, 133, 186, 145), fill=colour)
    draw.text((24, 23), 'ROOM / 01', fill=(130, 148, 173), font=FONT)
    for i, value in enumerate(state.display_bars):
        height = 3 + int(value*72) if not quiet else 3+int(6*pulse)
        x = 24+i*13
        box = (x, 294-height, x+8, 294)
        if hasattr(draw, 'rounded_rectangle'):
            draw.rounded_rectangle(box, radius=3, fill=colour)
        else:  # Pillow shipped with Raspberry Pi OS Buster
            draw.rectangle(box, fill=colour)
    label = 'MIC DISCONNECTED' if error else ('QUIET / %d BPM' % bpm if quiet else 'LISTENING')
    draw.text((24, 323), label, fill=(130, 148, 173), font=FONT)
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='plughw:CARD=Device,DEV=0')
    parser.add_argument('--framebuffer', default='/dev/fb0')
    parser.add_argument('--bpm', type=int, default=72)
    parser.add_argument('--noise-floor', type=float, default=.008)
    parser.add_argument('--preview', type=Path)
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument('--stats', action='store_true', help='Log achieved frame rate every ten seconds')
    parser.add_argument('--scene', type=Path, help='Validated daily drawing script')
    args = parser.parse_args()
    if not 1 <= args.fps <= 60:
        parser.error('--fps must be between 1 and 60')
    state = Analysis(args.noise_floor)
    daily = None
    if args.scene:
        from scenes import DailyScene
        daily = DailyScene(args.scene)
    if args.preview:
        t = np.arange(BLOCK)/RATE
        state.update((10000*np.sin(2*np.pi*440*t)).astype(np.int16), 1)
        state.animate(1)
        render(state, 1, args.bpm).resize((720, 720)).save(args.preview)
        return
    fb = Framebuffer(args.framebuffer)
    process = None
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        process = subprocess.Popen(['arecord', '-q', '-D', args.device, '-t', 'raw',
                                    '-f', 'S16_LE', '-r', str(RATE), '-c', '1'], stdout=subprocess.PIPE)
        os.set_blocking(process.stdout.fileno(), False)
        pending = bytearray()
        previous = stats_start = time.monotonic()
        frames = 0
        while running:
            now = time.monotonic()
            ready, _, _ = select.select([process.stdout], [], [], 0)
            if ready:
                pending.extend(os.read(process.stdout.fileno(), BLOCK*2*32))
            while len(pending) >= BLOCK*2:
                samples = np.frombuffer(bytes(pending[:BLOCK*2]), dtype='<i2')
                del pending[:BLOCK*2]
                state.update(samples, now)
            state.animate(now-previous)
            previous = now
            image = daily.render(state, now, args.bpm) if daily else None
            if image is None:
                image = render(state, now, args.bpm, process.poll() is not None)
            fb.show(image)
            frames += 1
            end = time.monotonic()
            if args.stats and end-stats_start >= 10:
                print('Frame rate: %.1f FPS; mic RMS %.5f; level %.3f; quiet %s' %
                      (frames/(end-stats_start), state.rms, state.display_level,
                       now-state.last_sound > 3), flush=True)
                stats_start, frames = end, 0
            time.sleep(max(0, 1/args.fps-(time.monotonic()-now)))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        fb.close()


if __name__ == '__main__':
    main()
