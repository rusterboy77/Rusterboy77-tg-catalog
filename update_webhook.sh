#!/bin/bash

# Espera hasta que el contenedor ngrok esté listo
while ! sudo docker exec ngrok curl -s http://localhost:4040/api/tunnels >/dev/null 2>&1; do
  echo "Esperando a que ngrok esté listo..."
  sleep 2
done

# Luego actualiza el webhook
NGROK_URL=$(sudo docker exec ngrok curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.name=="tg_catalog") | .public_url')
BOT_TOKEN=7629091414:AAFRskiLwIPfjgIxz9KZB88dyfbKU1LTsu8
curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" -d "url=$NGROK_URL"
echo "Webhook actualizado a $NGROK_URL"

