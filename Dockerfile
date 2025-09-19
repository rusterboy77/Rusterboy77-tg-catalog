# Imagen base ligera de Python
FROM python:3.12-slim

# Evitar buffering de stdout/stderr
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Copiar scripts y requirements
COPY app/ /app/

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Puerto para FastAPI
EXPOSE 8000

# Comando por defecto
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
