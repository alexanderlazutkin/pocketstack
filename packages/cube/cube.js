const path = require('path');

const WAREHOUSE = path.resolve(__dirname, '../../warehouse/pocketstack.duckdb');

module.exports = {
  driverFactory: () => ({
    type: 'duckdb',
    initSql: `ATTACH '${WAREHOUSE}' (READ_ONLY)`,
  }),
  apiSecret: process.env.CUBEJS_API_SECRET || 'pocketstack-demo-secret',
  sqlPort: 15432,
  sqlUser: process.env.CUBESQL_USER || 'sql-user',
  sqlPassword: process.env.CUBESQL_PASSWORD || 'sql-password',
};
