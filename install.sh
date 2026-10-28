#!/bin/sh
# Run with sudo from a staged copy on the Pi to install the on-device classic rotation.
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
id visdisplay >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin visdisplay
install -d -m 755 /opt/room-visualiser /var/lib/room-visualiser
for name in visualiser.py scenes.py classic_series.py validate_scene.py generate_daily.py schedule.py example_scene.py reactive_rain.py; do
    install -m 644 "$SOURCE/$name" /opt/room-visualiser/
done
install -m 644 "$SOURCE"/systemd/* /etc/systemd/system/
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/room-visualiser*.service /etc/systemd/system/room-visualiser*.timer
# Enable the timers separately after the display has been tested.
