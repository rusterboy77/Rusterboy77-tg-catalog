#!/bin/bash

NGROK_CONTAINER=ngrok
BOT_TOKEN=TU_TELEGRAM_BOT_TOKEN

# Espera a que ngrok esté listo
for i in {1..15}; do
  NGROK_URL=$(sudo docker exec $NGROK_CONTAINER curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.name=="tg_catalog") | .public_url')
  if [ -n "$NGROK_URL" ]; then
    break
  fi
  echo "Esperando a que ngrok inicie... ($i/15)"
  sleep 2
done

if [ -z "$NGROK_URL" ]; then
  echo "No se pudo obtener la URL de ngrok. Abortando."
  exit 1
fi

curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
     -d "url=$NGROK_URL"

echo "Webhook actualizado a $NGROK_URL"

