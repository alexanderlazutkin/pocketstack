const fs = require('fs');
const path = require('path');
const { DuckDBDriver } = require('@cubejs-backend/duckdb-driver');

const WAREHOUSE = path.resolve(__dirname, '../../warehouse/pocketstack.duckdb');
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
  apiSecret: process.env.CUBEJS_API_SECRET || 'pocketstack-demo-secret',
  sqlPort: 15432,
  sqlUser: process.env.CUBESQL_USER || 'sql-user',
  sqlPassword: process.env.CUBEJS_SQL_PASSWORD || 'sql-password',
};
