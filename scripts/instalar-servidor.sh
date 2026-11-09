#!/usr/bin/env bash
# =============================================================================
#  Instalación de la Gestoría en un servidor Ubuntu 22.04 / 24.04 recién creado.
#
#  Uso (como root o con sudo), desde la carpeta del proyecto:
#      sudo bash scripts/instalar-servidor.sh
#
#  Qué hace:
#    1. Instala Docker, certbot y actualizaciones automáticas de seguridad.
#    2. Cortafuegos: solo SSH (22), HTTP (80) y HTTPS (443).
#    3. Pide los datos de Supabase SIN mostrarlos ni guardarlos en el historial
#       y crea el .env (permisos 600).
#    4. Pide el certificado HTTPS de Let's Encrypt y deja la renovación automática.
#    5. Construye y arranca la aplicación, y crea el primer usuario de la gestoría.
#
#  Se puede volver a ejecutar: si el .env o el certificado ya existen, pregunta antes
#  de cambiarlos.
# =============================================================================
set -euo pipefail

ROJO=$'\e[31m'; VERDE=$'\e[32m'; AMARILLO=$'\e[33m'; NEGRITA=$'\e[1m'; FIN=$'\e[0m'
paso()  { echo; echo "${NEGRITA}==> $*${FIN}"; }
ok()    { echo "${VERDE}✓ $*${FIN}"; }
aviso() { echo "${AMARILLO}! $*${FIN}"; }
error() { echo "${ROJO}✗ $*${FIN}" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "Ejecuta el script con sudo: sudo bash scripts/instalar-servidor.sh"
[[ -f docker-compose.yml ]] || error "Ejecútalo desde la carpeta del proyecto (donde está docker-compose.yml)"
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || aviso "Probado en Ubuntu; en ${PRETTY_NAME:-este sistema} puede necesitar ajustes."
DIR="$(pwd)"

# -----------------------------------------------------------------------------
paso "1/6 Paquetes del sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 certbot ufw unattended-upgrades curl openssl >/dev/null
systemctl enable --now docker >/dev/null
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true
ok "Docker $(docker --version | cut -d' ' -f3 | tr -d ,), certbot y actualizaciones automáticas"

# -----------------------------------------------------------------------------
paso "2/6 Cortafuegos (solo 22, 80 y 443)"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ok "$(ufw status | head -1)"

# -----------------------------------------------------------------------------
paso "3/6 Configuración (.env)"
crear_env=s
if [[ -f .env ]]; then
  read -rp "Ya existe un .env. ¿Sustituirlo? (s/N): " crear_env
  crear_env=${crear_env:-n}
fi
if [[ "$crear_env" =~ ^[sS]$ ]]; then
  read -rp "Dominio de la aplicación (ej. gestoria.tudominio.es): " DOMINIO
  [[ -n "$DOMINIO" ]] || error "El dominio es obligatorio"
  read -rp "URL del proyecto Supabase [https://fgjoafbpejgrbnjsufvi.supabase.co]: " SUPABASE_URL
  SUPABASE_URL=${SUPABASE_URL:-https://fgjoafbpejgrbnjsufvi.supabase.co}
  REF=$(echo "$SUPABASE_URL" | sed -E 's#https://([^.]+)\..*#\1#')
  echo "Clave secreta de Supabase solo para la gestoría (empieza por sb_secret_). No se mostrará:"
  read -rs SUPABASE_SECRET_KEY; echo
  [[ "$SUPABASE_SECRET_KEY" == sb_secret_* || "$SUPABASE_SECRET_KEY" == eyJ* ]] || error "Eso no parece una clave secreta de Supabase"
  echo "Host del Session pooler (Supabase > Connect > Session pooler, ej. aws-0-eu-west-1.pooler.supabase.com):"
  read -r POOLER
  [[ "$POOLER" == *pooler.supabase.com ]] || aviso "El host no termina en pooler.supabase.com: revisa que sea el Session pooler"
  echo "Contraseña del rol gestoria_api (la que pusiste con ALTER ROLE). No se mostrará:"
  read -rs DB_PASS; echo
  [[ ${#DB_PASS} -ge 16 ]] || error "Usa una contraseña de al menos 16 caracteres para gestoria_api"
  DB_PASS_URL=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$DB_PASS")
  SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-64)
  umask 077
  cat > .env <<EOF
DOMINIO=${DOMINIO}
SECRET_KEY=${SECRET_KEY}
SUPABASE_URL=${SUPABASE_URL}
SUPABASE_SECRET_KEY=${SUPABASE_SECRET_KEY}
DATABASE_URL=postgresql+psycopg2://gestoria_api.${REF}:${DB_PASS_URL}@${POOLER}:5432/postgres
MAX_UPLOAD_MB=10
EOF
  chmod 600 .env
  unset SUPABASE_SECRET_KEY DB_PASS DB_PASS_URL SECRET_KEY
  ok ".env creado (permisos 600)"
fi
DOMINIO=$(grep '^DOMINIO=' .env | cut -d= -f2-)
[[ -n "$DOMINIO" ]] || error "Falta DOMINIO en .env"

mkdir -p certs certbot-www
chmod 700 certs
if [[ ! -s certs/supabase-ca.crt ]]; then
  aviso "Falta el certificado SSL de la base de datos en ${DIR}/certs/supabase-ca.crt"
  echo "  Descárgalo en Supabase > Database > Settings > SSL Configuration y súbelo, por ejemplo:"
  echo "  scp prod-ca-2021.crt usuario@servidor:${DIR}/certs/supabase-ca.crt"
  read -rp "Pulsa Enter cuando esté subido... "
  [[ -s certs/supabase-ca.crt ]] || error "No encuentro certs/supabase-ca.crt"
fi
openssl x509 -in certs/supabase-ca.crt -noout >/dev/null 2>&1 || error "certs/supabase-ca.crt no es un certificado válido"
ok "Certificado de Supabase presente"

# -----------------------------------------------------------------------------
paso "4/6 Certificado HTTPS para ${DOMINIO}"
IP_PUBLICA=$(curl -s4 --max-time 5 https://ifconfig.me || true)
IP_DNS=$(getent ahostsv4 "$DOMINIO" | awk 'NR==1{print $1}' || true)
if [[ -n "$IP_PUBLICA" && "$IP_DNS" != "$IP_PUBLICA" ]]; then
  aviso "El dominio ${DOMINIO} apunta a '${IP_DNS:-nada}' y este servidor es ${IP_PUBLICA}."
  aviso "Crea un registro DNS tipo A de ${DOMINIO} hacia ${IP_PUBLICA} y espera a que se propague."
  read -rp "¿Continuar de todos modos? (s/N): " seguir; [[ "$seguir" =~ ^[sS]$ ]] || exit 1
fi
if [[ ! -s "/etc/letsencrypt/live/${DOMINIO}/fullchain.pem" ]]; then
  read -rp "Email para avisos de Let's Encrypt (caducidad del certificado): " EMAIL
  docker compose stop nginx >/dev/null 2>&1 || true     # el puerto 80 tiene que estar libre
  certbot certonly --standalone --non-interactive --agree-tos -m "$EMAIL" -d "$DOMINIO"
fi
cp -L "/etc/letsencrypt/live/${DOMINIO}/fullchain.pem" "/etc/letsencrypt/live/${DOMINIO}/privkey.pem" certs/
chmod 600 certs/privkey.pem
# Renovación automática: certbot renueva y este hook copia el certificado y recarga Nginx
cat > /etc/letsencrypt/renewal-hooks/deploy/gestoria.sh <<EOF
#!/bin/sh
cp -L /etc/letsencrypt/live/${DOMINIO}/fullchain.pem /etc/letsencrypt/live/${DOMINIO}/privkey.pem ${DIR}/certs/
chmod 600 ${DIR}/certs/privkey.pem
cd ${DIR} && docker compose restart nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/gestoria.sh
# en modo standalone la renovación necesita el puerto 80: se para Nginx un momento
sed -i 's/^authenticator = .*/authenticator = standalone/' "/etc/letsencrypt/renewal/${DOMINIO}.conf" 2>/dev/null || true
grep -q '^pre_hook' "/etc/letsencrypt/renewal/${DOMINIO}.conf" || cat >> "/etc/letsencrypt/renewal/${DOMINIO}.conf" <<EOF
pre_hook = cd ${DIR} && docker compose stop nginx
post_hook = cd ${DIR} && docker compose start nginx
EOF
systemctl enable --now certbot.timer >/dev/null 2>&1 || true
ok "Certificado listo y renovación automática configurada"

# -----------------------------------------------------------------------------
paso "5/6 Construir y arrancar la aplicación (la primera vez tarda unos minutos)"
docker compose up -d --build
echo -n "Esperando a que la API esté sana"
for _ in $(seq 1 40); do
  estado=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api)" 2>/dev/null || echo "?")
  [[ "$estado" == "healthy" ]] && break
  echo -n "."; sleep 3
done; echo
if [[ "$estado" != "healthy" ]]; then
  docker compose logs --tail 40 api
  error "La API no arranca. Revisa los mensajes de arriba (datos de conexión, contraseña o certificado)."
fi
curl -fsS "https://${DOMINIO}/api/salud" >/dev/null && ok "https://${DOMINIO} responde" \
  || aviso "La API está sana pero https://${DOMINIO} no responde todavía (¿DNS?). Revisa: docker compose logs nginx"

# -----------------------------------------------------------------------------
paso "6/6 Primer usuario de la gestoría"
read -rp "¿Crear ahora tu usuario de gestor? (S/n): " crear
if [[ ! "${crear:-s}" =~ ^[nN]$ ]]; then
  read -rp "Email: " EMAIL_G
  read -rp "Nombre: " NOMBRE_G
  docker compose exec api python -m app.crear_gestor "$EMAIL_G" "$NOMBRE_G"
fi

echo
ok "${NEGRITA}Instalación terminada${FIN}"
echo "  Gestoría y administración de clientes:  https://${DOMINIO}"
echo "  App móvil (compras y ventas):           https://${DOMINIO}/movil"
echo "  Ver logs:        docker compose logs -f"
echo "  Actualizar:      git pull && docker compose up -d --build"
