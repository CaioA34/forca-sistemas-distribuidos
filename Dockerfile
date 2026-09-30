FROM python:3.12.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --no-create-home forca
COPY forca ./forca
COPY web ./web
COPY servidor.py gateway.py cliente.py ./
USER forca
EXPOSE 5000 5001 8080
# O mesmo pacote serve ao nó (padrão) e ao gateway (command: python gateway.py).
CMD ["python", "servidor.py"]
