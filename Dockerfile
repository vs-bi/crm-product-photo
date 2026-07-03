FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8501 8000

ENTRYPOINT ["bash", "entrypoint.sh"]
