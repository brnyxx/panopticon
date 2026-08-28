ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.8.13@sha256:4de5495181a281bc744845b9579acf7b221d6791f99bcc211b9ec13f417c2853
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE}
USER root
RUN printf '%s\n' \
      'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260825T000000Z bookworm main' \
      'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/20260825T000000Z bookworm-security main' \
      > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates dnsmasq git iptables procps strace tinyproxy \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /uvx /usr/local/bin/
RUN useradd -m -u 1000 -s /bin/bash pano
COPY entrypoint.sh /usr/local/bin/pano-entry
COPY tinyproxy.conf /etc/tinyproxy/pano.conf
RUN chmod +x /usr/local/bin/pano-entry
USER pano
WORKDIR /home/pano
ENTRYPOINT ["/usr/local/bin/pano-entry"]
