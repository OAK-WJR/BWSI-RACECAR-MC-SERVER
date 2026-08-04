# Sandbox image for running student racecar code.
# Built once by scripts/race-runner.sh; see sim/README.md.
FROM python:3.12-slim

RUN pip install --no-cache-dir \
        numpy==2.1.3 \
        opencv-python-headless==4.10.0.84 \
        pyyaml==6.0.2

# The simulator itself is bind-mounted read-only at /sim, so an edit there
# takes effect without a rebuild.
WORKDIR /job
