FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/

ENV HOST=0.0.0.0
ENV PORT=9000
ENV LOG_LEVEL=info

EXPOSE 9000

CMD ["uv", "run", "python", "-m", "lusid_mock"]
