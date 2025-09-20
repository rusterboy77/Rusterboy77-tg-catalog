#!/bin/sh
# Espera que ngrok esté listo
sleep 5

# Obtener URL pública del túnel
URL=$(curl -s http://127.0.0.1:4040/api/tunnels | jq -r '.tunnels[0].public_url')

# Actualizar webhook de Telegram
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook?url=$URL/tg_catalog"

echo "Webhook actualizado: $URL/tg_catalog"
