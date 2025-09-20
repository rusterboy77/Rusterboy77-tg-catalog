#!/bin/bash

# Nombre del contenedor ngrok
NGROK_CONTAINER=ngrok

# Token del bot de Telegram
BOT_TOKEN=7629091414:AAFRskiLwIPfjgIxz9KZB88dyfbKU1LTsu8

# Consulta la URL pública del túnel tg_catalog
NGROK_URL=$(sudo docker exec $NGROK_CONTAINER curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.name=="tg_catalog") | .public_url')

# Actualiza el webhook de Telegram
curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
     -d "url=$NGROK_URL"

echo "Webhook actualizado a $NGROK_URL"
