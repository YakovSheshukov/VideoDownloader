FROM python:3.9-slim

# Установка необходимых системных пакетов
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка зависимостей Python
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создание директории для загрузок
RUN mkdir -p downloads

# Запуск бота
CMD ["python", "test.py"] 