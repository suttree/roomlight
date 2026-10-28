"""Keep the display and microphone running at every hour."""
import argparse
import datetime
import os
import subprocess
import time
from pathlib import Path


def awake(hour):
    return True


def reconcile(force=None):
    os.environ['TZ'] = 'Europe/London'
    time.tzset()
    enabled = awake(datetime.datetime.now().hour) if force is None else force
    brightness = Path('/sys/class/backlight/rpi_backlight/brightness')
    if enabled:
        if brightness.exists():
            brightness.write_text('1')
        subprocess.run(['systemctl', 'start', 'room-visualiser.service'], check=True)
    else:
        subprocess.run(['systemctl', 'stop', 'room-visualiser.service'], check=True)
        if brightness.exists():
            brightness.write_text('0')
    return enabled


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', choices=['on', 'off'])
    args = parser.parse_args()
    reconcile(None if args.test is None else args.test == 'on')
