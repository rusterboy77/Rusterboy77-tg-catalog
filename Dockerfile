FROM ngrok/ngrok:latest

# Instalar jq y curl si no están
RUN apt-get update && apt-get install -y jq curl

# Copiar script de actualización de webhook
COPY update_webhook.sh /update_webhook.sh
RUN chmod +x /update_webhook.sh

# Arranque automático: ngrok + actualización webhook
ENTRYPOINT sh -c "ngrok start --all --config /var/lib/ngrok/ngrok.yml & sleep 5 && /update_webhook.sh && tail -f /dev/null"

