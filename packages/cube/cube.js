const fs = require('fs');
const path = require('path');
const { DuckDBDriver } = require('@cubejs-backend/duckdb-driver');

const WAREHOUSE = path.resolve(__dirname, '../../warehouse/pocketstack.duckdb');

// Режим хранилища (Stage 7): file (основной) | ducklake (pg-каталог + MinIO).
// Переключатель — WAREHOUSE_MODE в .env (см. .env.example).
const WAREHOUSE_MODE = process.env.WAREHOUSE_MODE || 'file';
if (!['file', 'ducklake'].includes(WAREHOUSE_MODE)) {
  throw new Error(`Неизвестный WAREHOUSE_MODE=${WAREHOUSE_MODE} (допустимо file|ducklake)`);
}

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

  // DuckLake (Stage 7, шаг 5): init на КАЖДОМ коннекте пула — ATTACH/SET суть
  // свойства сессии; инициализация только одного коннекта даёт «плавающие»
  // ошибки на части запросов. Каталог цепляем READ_ONLY: защита от случайной
  // AUTOMATIC_MIGRATION со стороны читателя (docs/plan.md Stage 7).
  async configureConnection(connection) {
    await super.configureConnection(connection);
    if (WAREHOUSE_MODE !== 'ducklake') return;

    const run = (sql) => connection.run(sql);
    for (const ext of ['httpfs', 'postgres', 'ducklake']) {
      try {
        await run(`LOAD ${ext}`);
      } catch (_) {
        await run(`INSTALL ${ext}`);
        await run(`LOAD ${ext}`);
      }
    }
    for (const sql of [
      `SET s3_endpoint='${requiredEnv('DUCKLAKE_S3_ENDPOINT')}'`,
      'SET s3_use_ssl=false',
      "SET s3_url_style='path'",
      `SET s3_access_key_id='${requiredEnv('DUCKLAKE_S3_ACCESS_KEY')}'`,
      `SET s3_secret_access_key='${requiredEnv('DUCKLAKE_S3_SECRET_KEY')}'`,
    ]) {
      await run(sql);
    }
    const dsn =
      `postgres:dbname=${requiredEnv('DUCKLAKE_PG_DB')}` +
      ` user=${requiredEnv('DUCKLAKE_PG_USER')} password=${requiredEnv('DUCKLAKE_PG_PASSWORD')}` +
      ` host=${requiredEnv('DUCKLAKE_PG_HOST')} port=${requiredEnv('DUCKLAKE_PG_PORT')}`;
    const dataPath = `s3://${requiredEnv('DUCKLAKE_S3_BUCKET')}/`;
    // Алиас = pocketstack: семантическая модель адресует хранилище по логическому
    // имени каталога (pocketstack.marts.*) — одинаково в file- и ducklake-режимах
    await run(
      `ATTACH '${dsn}' AS pocketstack (TYPE ducklake, DATA_PATH '${dataPath}', READ_ONLY)`
    );
    await run('USE pocketstack');
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
  // file: initSql аттачит локальный файл READ_ONLY (основной режим);
  // ducklake: инициализация каждого коннекта — в TimingDuckDBDriver
  // .configureConnection (ATTACH lake READ_ONLY + USE lake), см. Stage 7 шаг 5.
  driverFactory: () =>
    new TimingDuckDBDriver(
      WAREHOUSE_MODE === 'ducklake' ? {} : { initSql: `ATTACH '${WAREHOUSE}' (READ_ONLY)` }
    ),
  apiSecret: requiredEnv('CUBEJS_API_SECRET'),
  sqlPort: 15432,
  // pg-wire (psql/psycopg): в dev mode порт 15432 подразумевается, в прод — нет.
  pgSqlPort: 15432,
  // Без Cube Store: в прод-режиме Cube по умолчанию хочет его для очереди/кэша —
  // локальное DuckDB-демо работает целиком in-memory.
  cacheAndQueueDriver: 'memory',

  // --- RBAC (docs/cube-rbac.md) ---------------------------------------------
  // Группы назначаются ТОЛЬКО из подписанного контекста:
  //  REST (:4000)   — claims JWT (scripts/make-cube-token.py) → securityContext;
  //  SQL API (:15432) — securityContext назначает checkSqlAuth по учётке.
  // Прод-режим Cube принимает только подписанные JWT (сырой секрет → 403),
  // поэтому непрошедший авторизацию запрос сюда вообще не доходит.
  // ВАЖНО: access_policy применяется и в dev-режиме — Playground ходит без
  // токена, групп нет → deny by default (WHERE 1=0). Dev-фолбэк ниже делает
  // безтокенный запрос admin'ом; запрос с user-токеном режется как в проде.
  // Дальше режут access_policy в модели (views/sales.view.yml + кубы факта);
  // группа без политики = deny by default.
  contextToGroups: async (context) => {
    const groups = context && context.securityContext && context.securityContext.groups;
    const parsed = Array.isArray(groups) ? groups.filter((g) => typeof g === 'string') : [];
    if (process.env.CUBEJS_DEV_MODE === 'true' && parsed.length === 0) {
      return ['admin'];
    }
    return parsed;
  },

  // Per-role учётки SQL API: креды в .env, группы — в securityContext.
  checkSqlAuth: async (req, user, password) => {
    const accounts = {
      [requiredEnv('CUBESQL_USER')]: {
        password: requiredEnv('CUBESQL_PASSWORD'),
        superuser: true,
        securityContext: { groups: ['admin'] },
      },
      [requiredEnv('CUBESQL_RBAC_USER')]: {
        password: requiredEnv('CUBESQL_RBAC_PASSWORD'),
        superuser: false,
        securityContext: {
          groups: ['user'],
          region: process.env.CUBE_RBAC_USER_REGION || 'AFRICA',
        },
      },
    };
    const account = accounts[user];
    if (!account) {
      throw new Error(`SQL API: пользователь "${user}" не существует`);
    }
    if (password !== account.password) {
      throw new Error(`SQL API: пароль не подходит для "${user}"`);
    }
    return {
      password,
      superuser: account.superuser,
      securityContext: account.securityContext,
    };
  },
};
