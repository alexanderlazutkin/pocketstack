const fs = require('fs');
const path = require('path');
const { DuckDBDriver } = require('@cubejs-backend/duckdb-driver');

const WAREHOUSE = path.resolve(__dirname, '../../warehouse/pocketstack.duckdb');

// Секреты — ТОЛЬКО из окружения (.env из корня репо, см. .env.example).
// Загружаем .env без перезаписи уже установленных переменных.
(function loadDotenv() {
  const envPath = path.resolve(__dirname, '../../.env');
  try {
    for (const raw of fs.readFileSync(envPath, 'utf8').split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('#')) continue;
      const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
      if (!m) continue;
      const value = m[2].trim().replace(/^["']|["']$/g, '');
      if (!(m[1] in process.env)) process.env[m[1]] = value;
    }
  } catch (_) {
    // .env опционален, если переменные заданы снаружи (CI)
  }
})();

// Обязательная переменная: без значения — понятная ошибка, никаких фолбэков.
function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Не задана переменная окружения ${name}. ` +
        'Скопируйте .env.example → .env в корне репо и заполните (docs/user-guide.md §1). ' +
        'Секреты в коде не хранятся.'
    );
  }
  return value;
}
// Ground truth для harness (Stage 3) + тайминги реальных запросов.
// Обёртка драйвера пишет в лог КАЖДЫЙ исполненный запрос одной строкой:
//   started_at,finished_at,duration_ms,status,sql
// (sql схлопнут в одну строку; started/finished — ISO-8601 UTC с мс; статус OK/ERR).
// Парсер harness ищет в логе SQL из /v1/sql — префиксные поля не мешают поиску.
const QUERY_LOG =
  process.env.CUBEJS_DUCKDB_QUERY_LOG ||
  path.resolve(__dirname, '../../artifacts/duckdb_query_log.csv');

class TimingDuckDBDriver extends DuckDBDriver {
  async query(queryText, values, options) {
    const startedAt = new Date();
    try {
      const res = await super.query(queryText, values, options);
      logQuery(startedAt, new Date(), 'OK', queryText);
      return res;
    } catch (e) {
      logQuery(startedAt, new Date(), 'ERR', queryText);
      throw e;
    }
  }
}

function logQuery(startedAt, finishedAt, status, queryText) {
  try {
    const sql = String(queryText).replace(/\s+/g, ' ').trim();
    fs.appendFileSync(
      QUERY_LOG,
      `${startedAt.toISOString()},${finishedAt.toISOString()},${
        finishedAt - startedAt
      },${status},${sql}\n`
    );
  } catch (_) {
    // лог не должен ломать исполнение запросов
  }
}

module.exports = {
  driverFactory: () =>
    new TimingDuckDBDriver({
      initSql: `ATTACH '${WAREHOUSE}' (READ_ONLY)`,
    }),
  apiSecret: requiredEnv('CUBEJS_API_SECRET'),
  sqlPort: 15432,
  sqlUser: requiredEnv('CUBESQL_USER'),
  sqlPassword: requiredEnv('CUBESQL_PASSWORD'),
};
