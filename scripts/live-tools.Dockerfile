FROM node:24-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git ca-certificates curl
RUN python3 -m venv /opt/live && /opt/live/bin/pip install uv==0.12.10
ENV PATH="/opt/live/bin:${PATH}"
WORKDIR /workspace
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY config ./config
COPY install.sh ./install.sh
COPY scripts/live_tools.py ./scripts/live_tools.py
RUN uv sync --frozen --no-dev
CMD ["uv", "run", "--frozen", "--no-dev", "python", "scripts/live_tools.py", "--report", "/results/linux-docker.json"]
