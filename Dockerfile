FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 5000

#                                       1 instance of app, 8 threads for the app
#                                                          can handle sandbox containers or HTTP requests to the webapp
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "60", "ctrl:app"]
