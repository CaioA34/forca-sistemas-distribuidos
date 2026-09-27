FROM python:3.12.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY forca ./forca
COPY servidor.py cliente.py ./
EXPOSE 5000 5001
CMD ["python", "servidor.py"]
