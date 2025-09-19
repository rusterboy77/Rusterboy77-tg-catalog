FROM alpine:latest

RUN apk add --no-cache curl unzip bash

# Descargar ngrok
RUN curl -Lo /ngrok.zip https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip \
    && unzip /ngrok.zip -d / \
    && rm /ngrok.zip

# Copiar archivo de configuración
COPY ngrok.yml /root/.ngrok2/ngrok.yml

# Comando por defecto
CMD ["/ngrok", "start", "--all", "--log=stdout"]

