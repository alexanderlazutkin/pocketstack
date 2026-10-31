-- Категории/подкатегории товаров: aw_product_ratios (снежинка Product уже
-- развёрнута внутри куба: level=category|subcategory|product).
SELECT aw_product_ratios.level AS level, aw_product_ratios.member AS member,
       aw_product_ratios.category AS category,
       aw_product_ratios.internet_amount AS internet_amount,
       aw_product_ratios.reseller_amount AS reseller_amount,
       aw_product_ratios.amount AS sales_amount,
       aw_product_ratios.gross_profit AS gross_profit
FROM aw_product_ratios
