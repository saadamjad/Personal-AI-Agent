#!/bin/sh
# Runs as root at container start. Railway mounts the volume at /app/data
# *after* the image is built, overriding whatever ownership the Dockerfile
# set at build time — so the mount point needs to be re-chowned here, every
# start, before dropping to the unprivileged app user.
set -e

mkdir -p /app/data
chown -R appuser:appuser /app/data

exec gosu appuser "$@"
