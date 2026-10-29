# Evidence — serving-контейнер (вариант A, Stage 7 шаг 7).
# Строгий пин Node 20.19.0: системный 24.x ломает sveltekit/vite SSR
# (docs/gotchas.md «Установка/версии») — контейнер решает проблему пина навсегда.
FROM node:20.19.0-bookworm

WORKDIR /app
COPY packages/evidence/package.json packages/evidence/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY packages/evidence/ ./
RUN rm -f sources/cube/connection.yaml

COPY docker/evidence/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 3000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
