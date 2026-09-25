FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Normaliza finales de línea por si el repo se clona en Windows
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh \
    && useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["./entrypoint.sh"]
