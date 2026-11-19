FROM node:26-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.31.9-alpine
# The same non-root changes nginxinc/nginx-unprivileged makes, until it publishes 1.31.9
RUN sed -i '/^user /d; s,/run/nginx.pid,/tmp/nginx.pid,; s,/var/run/nginx.pid,/tmp/nginx.pid,' /etc/nginx/nginx.conf \
    && sed -i '/^http {/a \    client_body_temp_path /tmp/client_temp;\n    proxy_temp_path /tmp/proxy_temp;\n    fastcgi_temp_path /tmp/fastcgi_temp;\n    uwsgi_temp_path /tmp/uwsgi_temp;\n    scgi_temp_path /tmp/scgi_temp;' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /var/cache/nginx /etc/nginx/conf.d
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER nginx
EXPOSE 8080
