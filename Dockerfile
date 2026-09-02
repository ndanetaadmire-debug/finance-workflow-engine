FROM python:3.13-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir hatchling
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
USER app
EXPOSE 8000
CMD ["uvicorn", "fwe.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
