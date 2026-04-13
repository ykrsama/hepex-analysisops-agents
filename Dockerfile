FROM ghcr.io/astral-sh/uv:python3.12-bookworm

SHELL ["/bin/bash", "-c"]

WORKDIR /root
  RUN apt-get update \
   && apt-get install -y curl \
   && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
   && apt-get install -y sudo build-essential cmake xrootd-client xrootd-server python3-xrootd nodejs \
   && rm -rf /var/lib/apt/lists/*
 
WORKDIR /root/analysis
  RUN python -m venv .venv \
   && source .venv/bin/activate \
   && pip install xrootd atlasopenmagic uproot awkward vector matplotlib mplhep pyyaml tqdm \
   && python3 -c "import sys; from atlasopenmagic import install_from_environment; install_from_environment()"

WORKDIR /root
  # Install OpenHarness
  RUN curl -fsSL https://raw.githubusercontent.com/HKUDS/OpenHarness/main/scripts/install.sh | bash -s -- --from-source --with-channels
  
  # Monkey patch
  RUN sed -i 's/"max_tokens": request.max_tokens,/"max_completion_tokens": request.max_tokens,/g' /root/.openharness-src/src/openharness/api/openai_client.py \
   && export PATH=/root/.openharness-venv/bin:$PATH \
   && oh provider use openai-compatible
 
  COPY pyproject.toml README.md ./
  COPY src src
  COPY skills/sm-ana-aod /root/.openharness/skills
  COPY AGENTS.md AGENTS.md

  RUN uv sync

  ENTRYPOINT ["uv", "run", "src/server.py", "--log-level", "DEBUG"]
  CMD ["--host", "0.0.0.0"]
  EXPOSE 9009
