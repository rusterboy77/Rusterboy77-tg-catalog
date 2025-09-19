# Dockerfile
FROM alpine:latest

RUN apk add --no-cache curl unzip bash

# Descargar ngrok (v3)
RUN curl -Lo /ngrok.zip https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip \
    && unzip /ngrok.zip -d / \
    && rm /ngrok.zip

# Definir comando
CMD ["/ngrok", "http", "tg_catalog:8000", "--log=stdout"]

