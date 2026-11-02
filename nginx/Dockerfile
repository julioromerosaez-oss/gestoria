# 1) Compila el frontend (gestoría + web app móvil)
FROM node:22-alpine AS build
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) Nginx: TLS, cabeceras, rate limiting, frontend estático y proxy a la API
FROM nginx:1.27-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx/templates/ /etc/nginx/templates/
COPY nginx/snippets/ /etc/nginx/snippets/
COPY --from=build /web/dist /usr/share/nginx/html
ENV NGINX_ENVSUBST_FILTER="^(DOMINIO|API_UPSTREAM)$"
EXPOSE 80 443
