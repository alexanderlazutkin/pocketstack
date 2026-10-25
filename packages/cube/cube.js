const path = require('path');

const WAREHOUSE = path.resolve(__dirname, '../../warehouse/pocketstack.duckdb');
// Ground truth для harness (Stage 3): лог реальных запросов к DuckDB.
// Включается через CUBEJS_DUCKDB_QUERY_LOG=<path> (см. Justfile: just cube).
const QUERY_LOG = process.env.CUBEJS_DUCKDB_QUERY_LOG;

module.exports = {
  driverFactory: () => ({
    type: 'duckdb',
    initSql: [
      `ATTACH '${WAREHOUSE}' (READ_ONLY)`,
      ...(QUERY_LOG ? [`SET log_query_path='${QUERY_LOG}'`] : []),
    ].join('; '),
  }),
  apiSecret: process.env.CUBEJS_API_SECRET || 'pocketstack-demo-secret',
  sqlPort: 15432,
  sqlUser: process.env.CUBESQL_USER || 'sql-user',
  sqlPassword: process.env.CUBESQL_PASSWORD || 'sql-password',
};
