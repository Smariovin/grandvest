#!/bin/bash
ENVS=$(docker inspect n8n 2>/dev/null | grep -A30 Env | head -30)
RUNNING=$(docker inspect -f '{{.State.Running}}' n8n 2>/dev/null || echo false)
NEED=false
echo "$ENVS" | grep -q "N8N_SECURE_COOKIE=false" || NEED=true
echo "$ENVS" | grep -q "N8N_TIMEZONE=Europe/Moscow" || NEED=true
[ "$RUNNING" != "true" ] && NEED=true
if [ "$NEED" = "true" ]; then
  docker stop n8n 2>/dev/null; docker rm n8n 2>/dev/null
  docker run -d --name n8n --restart unless-stopped -p 5678:5678 \
    -v /opt/n8n/n8n_data:/home/node/.n8n \
    -v /data:/data \
    -e N8N_TIMEZONE=Europe/Moscow \
    -e GENERIC_TIMEZONE=Europe/Moscow \
    -e N8N_SECURE_COOKIE=false \
    n8nio/n8n:latest
  sleep 20
  echo "RECREATED"
else
  echo "ALL OK"
fi
