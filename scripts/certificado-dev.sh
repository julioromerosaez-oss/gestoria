#!/usr/bin/env sh
# Certificado autofirmado SOLO para probar en local (https://localhost).
# En producción usa Let's Encrypt (ver README).
set -e
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout certs/privkey.pem -out certs/fullchain.pem \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost"
echo "Certificado de desarrollo creado en ./certs"
