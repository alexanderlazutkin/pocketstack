#!/usr/bin/env bash
# pocketstack — управление стеком (Cube :4000/:15432 + Evidence :3000).
# Полное руководство: docs/user-guide.md; установка с нуля: README.md.
#
#   scripts/stack.sh up              # поднять Cube + Evidence (с ожиданием здоровья)
#   scripts/stack.sh down            # остановить всё (СНИМАЕТ БЛОКИРОВКУ DuckDB)
#   scripts/stack.sh status          # состояние портов/процессов
#   scripts/stack.sh restart         # down + up
#   scripts/stack.sh sources         # перематериализовать Evidence sources (нужен Cube)
#   scripts/stack.sh rebuild [SF]    # ПОЛНОЕ пересоздание БД с нуля при sf=SF
#                                    #   (default 1): down → rename бэкап → dbgen →
#                                    #   sqlmesh → up → sources → rm бэкап.
#                                    #   Транзакционно: сбой → авто-восстановление
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$REPO_ROOT/artifacts/run"
LOG_DIR="$REPO_ROOT/artifacts/logs"
NODE20="$HOME/.local/opt/node-v20.19.0-linux-x64/bin"
CUBE_LOG="$LOG_DIR/cube.log"
EV_LOG="$LOG_DIR/evidence.log"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$REPO_ROOT/artifacts"

log()  { printf '%s %s\n' "$(date +%H:%M:%S)" "$*"; }
die()  { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }

port_up() { curl -s -o /dev/null --max-time 2 "$1" && return 0 || return 1; }
tcp_up()  { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3>&- 3<&-; return 0; } || return 1; }

wait_port() { # url label [попыток]
    local url="$1" label="$2" tries="${3:-60}"
    for _ in $(seq "$tries"); do
        port_up "$url" && { log "$label: готов ($url)"; return 0; }
        sleep 1
    done
    die "$label не поднялся за ${tries}s — см. лог (artifacts/logs/)"
}

stop_pidfile() { # name pidfile — убить группу процессов (setsid)
    local pf="$1"
    [ -f "$pf" ] || return 0
    local pid; pid="$(cat "$pf")"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        for _ in $(seq 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
        kill -KILL -- "-$pid" 2>/dev/null || true
        log "остановлен pid=$pid"
    fi
    rm -f "$pf"
}

ensure_node20() {
    [ -x "$NODE20/node" ] || die "Node 20 не найден: $NODE20/node
Установите (user-local, без глобальных изменений):
  mkdir -p ~/.local/opt && cd ~/.local/opt
  curl -fsSLO https://nodejs.org/dist/v20.19.0/node-v20.19.0-linux-x64.tar.xz
  tar xf node-v20.19.0-linux-x64.tar.xz && rm node-v20.19.0-linux-x64.tar.xz
Подробнее: docs/evidence-setup.md §0"
}

cmd_up() {
    # Cube
    if port_up http://localhost:4000; then
        log "Cube уже работает (:4000)"
    else
        log "Cube: запускаю..."
        ( cd "$REPO_ROOT/packages/cube" && \
          setsid nohup env CUBEJS_DUCKDB_QUERY_LOG="$REPO_ROOT/artifacts/duckdb_query_log.csv" \
          npm run dev > "$CUBE_LOG" 2>&1 & echo $! > "$RUN_DIR/cube.pid" )
        wait_port http://localhost:4000 "Cube" 90
    fi
    # Evidence
    ensure_node20
    if port_up http://localhost:3000; then
        log "Evidence уже работает (:3000)"
    else
        log "Evidence: запускаю..."
        ( cd "$REPO_ROOT/packages/evidence" && \
          setsid nohup env PATH="$NODE20:$PATH" \
          npm run dev > "$EV_LOG" 2>&1 & echo $! > "$RUN_DIR/evidence.pid" )
        wait_port http://localhost:3000 "Evidence" 90
    fi
    log "Стек поднят: Cube UI http://localhost:4000 · Evidence http://localhost:3000"
}

cmd_down() {
    stop_pidfile "$RUN_DIR/evidence.pid"
    stop_pidfile "$RUN_DIR/cube.pid"
    # Фолбэк: процессы без pidfile (запущены вручную, а не скриптом)
    pkill -f "node_modules/.bin/cubejs" 2>/dev/null || true
    pkill -f "cubestored" 2>/dev/null || true
    pkill -f "node_modules/.bin/evidence" 2>/dev/null || true
    pkill -f "vite dev --port 3000" 2>/dev/null || true
    sleep 1
    port_up http://localhost:4000 && log "ВНИМАНИЕ: :4000 всё ещё занят — найдите процесс вручную (lsof -i :4000)" || log "Cube остановлен"
    port_up http://localhost:3000 && log "ВНИМАНИЕ: :3000 всё ещё занят — найдите процесс вручную (lsof -i :3000)" || log "Evidence остановлен"
    log "Блокировка DuckDB снята (если держали серверы) — можно `just apply`"
}

cmd_status() {
    for spec in "Cube:http:4000" "Evidence:http:3000" "SQLAPI:tcp:15432"; do
        name="${spec%%:*}"; rest="${spec#*:}"; kind="${rest%%:*}"; port="${rest##*:}"
        if [ "$kind" = http ]; then port_up "http://localhost:$port" && st=UP || st=down
        else tcp_up "$port" && st=UP || st=down; fi
        printf '%-10s :%-5s %s\n' "$name" "$port" "$st"
    done
    for pf in cube evidence; do
        [ -f "$RUN_DIR/$pf.pid" ] && printf '%-10s pid=%s (stack.sh)\n' "$pf" "$(cat "$RUN_DIR/$pf.pid")"
    done
    [ -f "$REPO_ROOT/warehouse/pocketstack.duckdb" ] \
        && log "warehouse/pocketstack.duckdb: $(du -h "$REPO_ROOT/warehouse/pocketstack.duckdb" | cut -f1)"
}

cmd_sources() {
    port_up http://localhost:4000 || die "Cube не работает — сначала: scripts/stack.sh up"
    ensure_node20
    log "Материализация Evidence sources из Cube..."
    ( cd "$REPO_ROOT/packages/evidence" && env PATH="$NODE20:$PATH" npm run sources )
}

cmd_rebuild() {
    local sf="${1:-1}"
    log "rebuild sf=$sf: остановка стека (снятие блокировки DuckDB)..."
    cmd_down
    # Транзакционная замена БД: rename старой → создать новую → при успехе удалить
    # бэкап, при неудаче — авто-восстановление старой. Без rm «в лоб»: неудачный
    # rebuild не оставляет проект без данных. rm БД до sqlmesh обязателен — иначе
    # кэш состояния сочтёт модели неизменными и витрины не перестроятся.
    local db="$REPO_ROOT/warehouse/pocketstack.duckdb" bak=""
    if [ -e "$db" ]; then
        bak="$db.bak.$(date +%Y%m%d%H%M%S)"
        log "Резервирование текущей БД → $(basename "$bak")"
        mv "$db" "$bak"
        [ -e "$db.wal" ] && mv "$db.wal" "$bak.wal" || true
    fi
    if
        ( cd "$REPO_ROOT" && uv run python packages/sqlmesh/seed_tpch.py "$sf" ) && \
        ( cd "$REPO_ROOT/packages/sqlmesh" && uv run sqlmesh plan --auto-apply --no-prompts )
    then
        if [ -n "$bak" ]; then rm -f "$bak" "$bak.wal"; log "Успех: бэкап удалён"; fi
    else
        log "Пересоздание НЕ удалось — восстанавливаю предыдущую БД..."
        rm -f "$db" "$db.wal"
        [ -n "$bak" ] && { mv "$bak" "$db"; [ -e "$bak.wal" ] && mv "$bak.wal" "$db.wal" || true; }
        die "Восстановлено из бэкапа. Причина сбоя — выше в логе; повторите: scripts/stack.sh rebuild $sf"
    fi
    cmd_up
    cmd_sources
    log "rebuild sf=$sf завершён (БД создана с нуля). Проверка: just verify, just bench."
    log "Числа на дашбордах при sf≠1 изменятся — сверьте РАВЕНСТВО трёх путей (docs/user-guide.md)."
}

case "${1:-}" in
    up)       cmd_up ;;
    down)     cmd_down ;;
    status)   cmd_status ;;
    restart)  cmd_down; cmd_up ;;
    sources)  cmd_sources ;;
    rebuild)  shift; cmd_rebuild "$@" ;;
    *)        grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -12; exit 1 ;;
esac
