FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home bot \
    && mkdir /data && chown 10001:10001 /data && chmod 700 /data
WORKDIR /app
COPY skills/us-immigration-casework/ /app/
COPY integrations/telegram/ruta-consular.jpg /app/ruta-consular.jpg
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "scripts/telegram_bot.py", "run", "--db", "/data/telegram.sqlite3"]
