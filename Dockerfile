FROM python:3.14-slim
LABEL maintainer="andreygomenuk@gmail.com"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /files/static

RUN adduser \
    --disabled-password \
    --no-create-home \
    my_user

RUN chown my_user /app \
    && chown -R my_user /files/static \
    && chmod -R 755 /files/static

USER my_user

EXPOSE 8000
