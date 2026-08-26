FROM pano-sandbox-base
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
USER pano
