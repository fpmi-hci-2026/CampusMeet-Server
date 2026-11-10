FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --uid 10001 --create-home campusmeet

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=campusmeet:campusmeet campusmeet ./campusmeet
COPY --chown=campusmeet:campusmeet web ./web
COPY --chown=campusmeet:campusmeet mobile ./mobile
COPY --chown=campusmeet:campusmeet api ./api
COPY --chown=campusmeet:campusmeet database ./database

RUN mkdir -p /app/data && chown -R campusmeet:campusmeet /app

USER campusmeet
EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"

CMD ["uvicorn", "campusmeet.app:app", "--host", "0.0.0.0", "--port", "8000"]
