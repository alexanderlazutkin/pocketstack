# Evidence: установка с нуля (Stage 4, runbook)

Консолидирует ВСЕ проблемы, решённые при развёртывании Evidence 40.1.8.
Каждый пункт ниже — следствие реального падения (детали и диагностика: `docs/gotchas.md`, раздел Evidence).

## 0. Предусловия

| Что | Требование | Почему |
|---|---|---|
| Node | **20.x** (проверено 20.19.0), локально в `~/.local/opt/node-v20.19.0-linux-x64/` | Системный Node 24 ломает SSR: `Cannot find module '__SERVER__/internal.js'` (sveltekit/vite) |
| npm | >=7 (в комплекте Node 20) | `overrides` в package.json |
| DuckDB-витрина | `warehouse/` собрана (`just seed && just plan && just apply`) | Evidence читает только материализованное |
| Cube dev | запущен (`just cube`, :4000 REST / :15432 pg-wire) | нужен ТОЛЬКО для материализации sources, не для рантайма страниц |
| Chrome (опция) | `~/.cache/puppeteer/chrome/…` | headless-проверка `scripts/visual-check.mjs` |

Установка Node 20 без глобальных изменений (user-local, как у нас):

```bash
mkdir -p ~/.local/opt && cd ~/.local/opt
curl -fsSLO https://nodejs.org/dist/v20.19.0/node-v20.19.0-linux-x64.tar.xz
tar xf node-v20.19.0-linux-x64.tar.xz && rm node-v20.19.0-linux-x64.tar.xz
```

Ничего не прописывать в PATH глобально — префикс на команду (см. §4).

## 1. Пакет уже в репо — изнутри репозитория

`packages/evidence` коммитится целиком (pages, sources, connection.yaml, package.json+lock).
С нуля внутри репо:

```bash
cd packages/evidence
PATH=~/.local/opt/node-v20.19.0-linux-x64/bin:$PATH npm ci --legacy-peer-deps
```

- Строго `npm ci` с_lock из шаблона: `npm install` сам резолвит несовместимые версии.
- `--legacy-peer-deps` обязателен (конфликт peer'ов дерева Evidence 40.1.8).

## 2. Если package пересоздаётся (шаблон, не из репо)

`npm create evidence@latest` **СЛОМАН** (create-evidence без bin, 404). Официальный путь:

```bash
git clone --depth 1 -b LEGACY https://github.com/evidence-dev/template packages/evidence
cd packages/evidence && rm -rf .git
```

Шаблон недоукомплектован — после `npm ci` доставить peer'ы руками (в коммите уже есть):

```bash
PATH=~/.local/opt/node-v20.19.0-linux-x64/bin:$PATH \
  npm i -D @sveltejs/vite-plugin-svelte@^3 autoprefixer --legacy-peer-deps
# vite-plugin-svelte@^3 — под svelte 4.2 / vite 5.4 (v4+ требует svelte 5)
```

Без них dev падает: `Could not resolve peer dependency "@sveltejs/vite-plugin-svelte"` →
затем `Cannot find module 'autoprefixer'` (postcss.config.cjs шаблона).

## 3. Конфигурация

- `connection.yaml` источника `cube` **генерируется из `.env`** скриптом
  `scripts/render-evidence-connection.sh` (вызывается `stack.sh up/sources` и
  `just evidence` автоматически): Evidence 40.1.8 не интерполирует `${VAR}` в
  connection.yaml. Шаблон с плейсхолдерами — `connection.yaml.example` (в git);
  сгенерированный файл с реальными кредами — вне git (.gitignore).
- Второй источник `duckdb_local` — read-only, без кредов (`filename` — путь
  ОТ каталога источника).
- Архитектура данных: страницы исполняют запросы в DuckDB-WASM в браузере поверх
  parquet из `.evidence/template/static/data/`; живой Cube трогается только материализацией.
  Поэтому вся метрика — в `sources/cube/*.sql` (golden-SQL дословно), страницы — тонкие
  `select * from cube.<id>` + `${inputs}`-фильтры.

## 4. Запуск (порядок обязателен)

```bash
# 1) Cube (нужен только для материализации)
PATH=$HOME/.local/bin:$PATH just cube &          # :4000/:15432

# 2) Материализация sources (22 таблицы; Cube должен быть поднят!)
cd packages/evidence
PATH=~/.local/opt/node-v20.19.0-linux-x64/bin:$PATH npm run sources

# 3) Dev-сервер страниц
PATH=~/.local/opt/node-v20.19.0-linux-x64/bin:$PATH npm run dev   # :3000
# то же одной командой: PATH=$HOME/.local/bin:$PATH just evidence
```

`just evidence` уже зашит на Node 20. Системный npm/node (24) стартовать нельзя.

## 5. Приёмка после установки

```bash
PATH=~/.local/opt/node-v20.19.0-linux-x64/bin:$PATH node scripts/visual-check.mjs
```

Критерий: 6/6 страниц, `errors: []` у каждой. Скриншоты — `/tmp/opencode/shots/`.

- `__data.json` в dev = `{"type":"data","nodes":[null,null]}` — **норма**
  (запросы исполняет DuckDB-WASM в браузере), данные проверять только через DOM.
- Метрики дашбордов обязаны совпадать с harness (`just verify`): Σ выручки на
  `/verification` = KPI `/revenue` = 218,102,223,885.00.

## 6. Требования к контенту страниц (зашитые грабли)

- Ссылки между страницами — ТОЛЬКО абсолютные: `[Верификация](/verification)`.
  Относительная `(verification)` с `/revenue` резолвится в `/revenue/verification` → 404.
- Проп `data` в компонентах — только в скобках: `data={query}`.
- `fmt=pct1` умножает на 100 (ждёт дробь); куб отдаёт rel_* в процент-пунктах → `fmt=num2`.
- `sort="revenue desc"` — направление только внутри кавычек.
- Golden-SQL без алиаса аггрегатов → колонка `"sum(sales.revenue)"` — алиасовать в v_*-обёртке.
- KPI-агрегаты — measures куба (метрики в Cube), НЕ BigValue summary* (их не существует).

## 7. Обновление данных

После `just apply` (sqlmesh) повторить §4 п.2 — sources перечитывают Cube.
Материализация read-only по DuckDB — с работающим Cube не конфликтует.
Перед `just apply` Cube останавливать (duckdb lock).
