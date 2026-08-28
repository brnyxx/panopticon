# Registry digest verified 2026-08-28; package indexes use an immutable Debian snapshot.
FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171
RUN printf '%s\n' \
      'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260825T000000Z bookworm main' \
      'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/20260825T000000Z bookworm-security main' \
      > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates dnsmasq git iptables procps strace tinyproxy \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 -s /bin/bash pano
COPY entrypoint.sh /usr/local/bin/pano-entry
COPY tinyproxy.conf /etc/tinyproxy/pano.conf
RUN chmod +x /usr/local/bin/pano-entry
USER pano
WORKDIR /home/pano
ENTRYPOINT ["/usr/local/bin/pano-entry"]
