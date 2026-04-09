FROM ghcr.io/astral-sh/uv:python3.13-bookworm

RUN adduser agent
USER agent
WORKDIR /home/agent

# Install OpenHarness
RUN curl -fsSL https://raw.githubusercontent.com/HKUDS/OpenHarness/main/scripts/install.sh | bash -s -- --from-source --with-channels

ENV PATH="/home/agent/.openharness-venv/bin:$PATH"

# Monkey patch
RUN sed -i 's/"max_tokens": request.max_tokens,/"max_completion_tokens": request.max_tokens,/g' /home/agent/.openharness-src/src/openharness/api/openai_client.py \
 && oh provider use openai-compatible

COPY --chown=agent:agent pyproject.toml uv.lock README.md ./
COPY --chown=agent:agent src src
COPY --chown=agent:agent skills/sm-ana-aod /home/agent/.openharness/skills
COPY --chown=agent:agent AGENTS.md AGENTS.md

RUN \
    --mount=type=cache,target=/home/agent/.cache/uv,uid=1000 \
    uv sync --locked


ENTRYPOINT ["uv", "run", "src/server.py", "--log-level", "DEBUG"]
CMD ["--host", "0.0.0.0"]
EXPOSE 9009
