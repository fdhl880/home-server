FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask requests

COPY . /app

EXPOSE 5000

ENV PORT=5000

CMD ["python", "server.py"]
