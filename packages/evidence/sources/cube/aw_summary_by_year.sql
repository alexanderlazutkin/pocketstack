-- Выручка по годам × канал: aw_sales_mov (месячный grain, агрегируем в год).
-- SQL API 1.8.13 не поддерживает cross-cube JOIN — используем одиночный куб,
-- где год и канал уже есть (ролевая дата предвычислена в подзапросе куба).
SELECT aw_sales_mov.year AS year, aw_sales_mov.channel AS channel,
       SUM(aw_sales_mov.revenue) AS sales_amount
FROM aw_sales_mov
GROUP BY aw_sales_mov.year, aw_sales_mov.channel
