# pano-sandbox-base: glibc + strace + dnsmasq + CA certs.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      strace dnsmasq ca-certificates iptables procps git \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 -s /bin/bash pano
COPY entrypoint.sh /usr/local/bin/pano-entry
RUN chmod +x /usr/local/bin/pano-entry
USER pano
WORKDIR /home/pano
ENTRYPOINT ["/usr/local/bin/pano-entry"]
