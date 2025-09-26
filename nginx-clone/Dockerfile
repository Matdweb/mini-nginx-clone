FROM python:3.11-slim
WORKDIR /app
COPY . .
# set PYTHONUNBUFFERED so logs appear immediately
ENV PYTHONUNBUFFERED=1
EXPOSE 80
CMD ["python", "mini-nginx.py"]
