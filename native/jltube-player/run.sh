#!/bin/sh
set -eu
# Mount in this service's private mount namespace. Failure must stop startup.
mount --make-rprivate /
mount --bind /run/jltube-player/resolv.conf /etc/resolv.conf
exec /var/opt/mgu-python/current/bin/python3 /var/opt/jltube-player/current/player.py serve
