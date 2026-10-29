# Cube — serving-контейнер (вариант A, Stage 7 шаг 7).
# node:24-bookworm — как на хосте (проверенная пара с драйвером);
# cubejs-server требует Node >= 22 (пин 20.19 — только для Evidence).
# Расширения duckdb печём в образ — рантайм без сети (LOAD из кэша).
# Секреты НЕ в образ: приходят env_file'ом (docker-compose), cube.js читает process.env.
FROM node:24-bookworm

WORKDIR /srv/packages/cube
COPY packages/cube/package.json packages/cube/package-lock.json ./
RUN npm ci
COPY packages/cube/cube.js ./
COPY packages/cube/model ./model

# Прогрев расширений под движок из lock (@duckdb/node-api 1.5.5): кэш ~/.duckdb
RUN node -e "\
  const A = require('@duckdb/node-api');\
  (async () => {\
    const i = await A.DuckDBInstance.create(':memory:');\
    const c = await i.connect();\
    for (const e of ['httpfs', 'postgres', 'ducklake']) await c.run('INSTALL ' + e);\
  })().catch((e) => { console.error(e); process.exit(1); });"

# /srv/warehouse — bind (file-режим, Cube ATTACH READ_ONLY);
# /srv/artifacts — bind (query-log = ground truth для harness)
ENV CUBEJS_DUCKDB_QUERY_LOG=/srv/artifacts/duckdb_query_log.csv
EXPOSE 4000 15432
CMD ["npm", "start"]
