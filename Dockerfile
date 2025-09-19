FROM alpine:latest

RUN apk add --no-cache curl unzip bash

# Descargar ngrok
RUN curl -Lo /ngrok.tgz https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz \
    && tar -xvzf /ngrok.tgz -C / \
    && rm /ngrok.tgz

# Copiar archivo de configuración
COPY ngrok.yml /root/.ngrok2/ngrok.yml

# Comando por defecto
CMD ["/ngrok", "start", "--all", "--log=stdout"]

