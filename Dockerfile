FROM python:3.12-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home campusmeet
COPY --chown=campusmeet:campusmeet campusmeet ./campusmeet
COPY --chown=campusmeet:campusmeet api/openapi.json ./api/openapi.json
COPY --chown=campusmeet:campusmeet database/schema.sqlite.sql ./database/schema.sqlite.sql
RUN mkdir /app/data && chown campusmeet:campusmeet /app/data
USER campusmeet
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=2)"
CMD ["python", "-m", "campusmeet.mock_api", "--host", "0.0.0.0"]
