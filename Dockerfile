# syntax=docker/dockerfile:1

# multimon-ng with the STQC demodulator, pinned to a commit of the fork.
ARG MULTIMON_REPO=https://github.com/marmurek/multimon-ng.git
ARG MULTIMON_REF=7b435bd122377f65c639bee0d9f8643fd582f278

FROM debian:trixie-slim AS multimon-build
ARG MULTIMON_REPO
ARG MULTIMON_REF
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --filter=blob:none "$MULTIMON_REPO" /src \
    && git -C /src checkout --detach "$MULTIMON_REF"
RUN cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release \
        -DX11_SUPPORT=OFF -DPULSE_AUDIO_SUPPORT=OFF -DSDL3_SCOPE=OFF \
    && cmake --build /build --parallel "$(nproc)"

FROM debian:trixie-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-websockets alsa-utils sox \
    && rm -rf /var/lib/apt/lists/*
COPY --from=multimon-build /build/multimon-ng /usr/local/bin/multimon-ng
COPY osp_decoder /opt/osp-decoder/osp_decoder
ENV PYTHONPATH=/opt/osp-decoder \
    PYTHONUNBUFFERED=1
# Group 29 is "audio" on Debian, Ubuntu and Raspberry Pi OS; it grants
# access to /dev/snd when the device is passed to the container.
RUN useradd --system --uid 990 --gid audio --no-create-home osp
USER osp
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python3 -m osp_decoder.healthcheck
ENTRYPOINT ["python3", "-m", "osp_decoder"]

# Development and test image: adds gen-ng and uv to run the test suite.
FROM runtime AS dev
USER root
COPY --from=multimon-build /build/gen-ng /usr/local/bin/gen-ng
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv
# Tests must import the mounted sources, not the copy installed for runtime.
ENV PYTHONPATH= \
    UV_PROJECT_ENVIRONMENT=/tmp/venv \
    UV_CACHE_DIR=/tmp/uv-cache \
    PYLINTHOME=/tmp/pylint
WORKDIR /work
ENTRYPOINT []
