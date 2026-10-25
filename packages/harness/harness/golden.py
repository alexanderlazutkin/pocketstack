"""Golden-вопросы: один вопрос — три представления.

- rest:      JSON для POST /v1/load (и /v1/sql)
- sqlapi:    SELECT поверх view `sales` через pg-wire :15432
             (врапперы по типу меры: SUM/AVG/COUNT/COUNT(DISTINCT))
- reference: эталонный SQL к marts.* в DuckDB (контракт витрины Stage 1b)

`ordered: true` — top-N вопрос: порядок строк входит в проверку.
Иначе сравнение — как отсортированное множество строк.
"""

_F = "marts.fact_sales f"

_REF_JOINS = {
    "customer": "JOIN marts.dim_customer c ON c.customer_id = f.customer_id",
    "supplier": "JOIN marts.dim_supplier s ON s.supplier_id = f.supplier_id",
    "part": "JOIN marts.dim_part p ON p.part_id = f.part_id",
    "order": "JOIN marts.dim_order o ON o.order_id = f.order_id",
    "date": "JOIN marts.dim_date d ON d.date_day = f.ship_date",
}

GOLDEN = [
    {
        "id": "total_revenue",
        "question": "Какова общая выручка за всё время?",
        "rest": {"measures": ["sales.revenue"]},
        "sqlapi": "SELECT SUM(sales.revenue) FROM sales",
        "reference": f"SELECT sum(f.net_price) FROM {_F}",
        "key_cols": 0,
    },
    {
        "id": "revenue_by_year",
        "question": "Какова выручка по годам (календарь отгрузок)?",
        "rest": {
            "measures": ["sales.revenue"],
            "dimensions": ["sales.year"],
            "order": {"sales.year": "asc"},
        },
        "sqlapi": "SELECT sales.year, SUM(sales.revenue) FROM sales "
        "GROUP BY sales.year ORDER BY sales.year",
        "reference": f"SELECT d.year, sum(f.net_price) FROM {_F} "
        f"{_REF_JOINS['date']} GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "revenue_by_region",
        "question": "Какова выручка по регионам клиентов?",
        "rest": {
            "measures": ["sales.revenue"],
            "dimensions": ["sales.customer_region"],
            "order": {"sales.customer_region": "asc"},
        },
        "sqlapi": "SELECT sales.customer_region, SUM(sales.revenue) FROM sales "
        "GROUP BY sales.customer_region ORDER BY sales.customer_region",
        "reference": f"SELECT c.customer_region, sum(f.net_price) FROM {_F} "
        f"{_REF_JOINS['customer']} GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "revenue_by_segment",
        "question": "Какова выручка по рыночным сегментам клиентов?",
        "rest": {
            "measures": ["sales.revenue"],
            "dimensions": ["sales.market_segment"],
            "order": {"sales.market_segment": "asc"},
        },
        "sqlapi": "SELECT sales.market_segment, SUM(sales.revenue) FROM sales "
        "GROUP BY sales.market_segment ORDER BY sales.market_segment",
        "reference": f"SELECT c.market_segment, sum(f.net_price) FROM {_F} "
        f"{_REF_JOINS['customer']} GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "orders_by_status",
        "question": "Сколько заказов по каждому статусу?",
        "rest": {
            "measures": ["sales.orders_count"],
            "dimensions": ["sales.order_status"],
            "order": {"sales.order_status": "asc"},
        },
        "sqlapi": "SELECT sales.order_status, COUNT(DISTINCT sales.orders_count) FROM sales "
        "GROUP BY sales.order_status ORDER BY sales.order_status",
        "reference": f"SELECT o.order_status, count(DISTINCT f.order_id) FROM {_F} "
        f"{_REF_JOINS['order']} GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "revenue_1997_by_quarter",
        "question": "Какова выручка по кварталам 1997 года?",
        "rest": {
            "measures": ["sales.revenue"],
            "dimensions": ["sales.quarter"],
            "filters": [{"member": "sales.year", "operator": "equals", "values": ["1997"]}],
            "order": {"sales.quarter": "asc"},
        },
        "sqlapi": "SELECT sales.quarter, SUM(sales.revenue) FROM sales "
        "WHERE sales.year = 1997 GROUP BY sales.quarter ORDER BY sales.quarter",
        "reference": f"SELECT d.quarter, sum(f.net_price) FROM {_F} "
        f"{_REF_JOINS['date']} WHERE d.year = 1997 GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "avg_discount_by_ship_mode",
        "question": "Каков средний дисконт по способам доставки?",
        "rest": {
            "measures": ["sales.avg_discount"],
            "dimensions": ["sales.ship_mode"],
            "order": {"sales.ship_mode": "asc"},
        },
        "sqlapi": "SELECT sales.ship_mode, AVG(sales.avg_discount) FROM sales "
        "GROUP BY sales.ship_mode ORDER BY sales.ship_mode",
        "reference": f"SELECT f.ship_mode, avg(f.discount) FROM {_F} GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "quantity_by_part_type_top10",
        "question": "Топ-10 типов деталей по суммарному количеству?",
        "rest": {
            "measures": ["sales.quantity"],
            "dimensions": ["sales.part_type"],
            "order": {"sales.quantity": "desc"},
            "limit": 10,
        },
        "sqlapi": "SELECT sales.part_type, SUM(sales.quantity) FROM sales "
        "GROUP BY sales.part_type ORDER BY SUM(sales.quantity) DESC LIMIT 10",
        "reference": f"SELECT p.part_type, sum(f.quantity) FROM {_F} "
        f"{_REF_JOINS['part']} GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
        "key_cols": 1,
        "ordered": True,
    },
    {
        "id": "revenue_by_supplier_region",
        "question": "Какова выручка по регионам поставщиков?",
        "rest": {
            "measures": ["sales.revenue"],
            "dimensions": ["sales.supplier_region"],
            "order": {"sales.supplier_region": "asc"},
        },
        "sqlapi": "SELECT sales.supplier_region, SUM(sales.revenue) FROM sales "
        "GROUP BY sales.supplier_region ORDER BY sales.supplier_region",
        "reference": f"SELECT s.supplier_region, sum(f.net_price) FROM {_F} "
        f"{_REF_JOINS['supplier']} GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "lines_by_return_flag",
        "question": "Сколько строк продаж по флагам возврата?",
        "rest": {
            "measures": ["sales.lines_count"],
            "dimensions": ["sales.return_flag"],
            "order": {"sales.return_flag": "asc"},
        },
        "sqlapi": "SELECT sales.return_flag, COUNT(sales.lines_count) FROM sales "
        "GROUP BY sales.return_flag ORDER BY sales.return_flag",
        "reference": f"SELECT f.return_flag, count(*) FROM {_F} GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "revenue_1996_by_month",
        "question": "Какова выручка по месяцам 1996 года?",
        "rest": {
            "measures": ["sales.revenue"],
            "dimensions": ["sales.month"],
            "filters": [{"member": "sales.year", "operator": "equals", "values": ["1996"]}],
            "order": {"sales.month": "asc"},
        },
        "sqlapi": "SELECT sales.month, SUM(sales.revenue) FROM sales "
        "WHERE sales.year = 1996 GROUP BY sales.month ORDER BY sales.month",
        "reference": f"SELECT d.month, sum(f.net_price) FROM {_F} "
        f"{_REF_JOINS['date']} WHERE d.year = 1996 GROUP BY 1 ORDER BY 1",
        "key_cols": 1,
    },
    {
        "id": "top5_customer_nations_by_revenue",
        "question": "Топ-5 стран клиентов по выручке?",
        "rest": {
            "measures": ["sales.revenue"],
            "dimensions": ["sales.customer_nation"],
            "order": {"sales.revenue": "desc"},
            "limit": 5,
        },
        "sqlapi": "SELECT sales.customer_nation, SUM(sales.revenue) FROM sales "
        "GROUP BY sales.customer_nation ORDER BY SUM(sales.revenue) DESC LIMIT 5",
        "reference": f"SELECT c.customer_nation, sum(f.net_price) FROM {_F} "
        f"{_REF_JOINS['customer']} GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
        "key_cols": 1,
        "ordered": True,
    },
    {
        "id": "sales_mov_1997",
        "question": "Каковы месячная выручка и отклонения YoY/PoP за 1997 (куб sales_mov)?",
        "rest": {
            "measures": ["sales_mov.revenue"],
            "dimensions": [
                "sales_mov.month",
                "sales_mov.revenue_ly",
                "sales_mov.rel_yoy",
                "sales_mov.rel_pop",
            ],
            "filters": [{"member": "sales_mov.year", "operator": "equals", "values": ["1997"]}],
            "order": {"sales_mov.month": "asc"},
        },
        "sqlapi": "SELECT sales_mov.month, sales_mov.revenue_ly, sales_mov.rel_yoy, "
        "sales_mov.rel_pop, SUM(sales_mov.revenue) FROM sales_mov WHERE sales_mov.year = 1997 "
        "GROUP BY sales_mov.month, sales_mov.revenue_ly, sales_mov.rel_yoy, sales_mov.rel_pop "
        "ORDER BY sales_mov.month",
        "reference": f"""
WITH m AS (
  SELECT d.year, d.month, sum(f.net_price) AS revenue
  FROM marts.fact_sales f JOIN marts.dim_date d ON d.date_day = f.ship_date
  GROUP BY 1, 2
)
SELECT cur.month, ly.revenue AS revenue_ly,
       100.0 * (cur.revenue - ly.revenue) / ly.revenue AS rel_yoy,
       100.0 * (cur.revenue - prev.revenue) / prev.revenue AS rel_pop,
       cur.revenue
FROM m cur
LEFT JOIN m ly ON ly.year = cur.year - 1 AND ly.month = cur.month
LEFT JOIN m prev ON prev.year = cur.year AND prev.month = cur.month - 1
WHERE cur.year = 1997
ORDER BY cur.month
""",
        "key_cols": 4,
    },
]
