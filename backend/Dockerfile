FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Копируем исходники целиком, затем ставим пакет с зависимостями.
# (pyproject объявляет packages=[app, ...], поэтому исходники должны быть на месте
#  ДО `pip install .` — иначе сборка setuptools падает.)
COPY . .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000
# Команда переопределяется в docker-compose (api vs worker).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
