SELECT aw_kpi.kpi, aw_kpi.member, aw_kpi.title, aw_kpi.folder,
       aw_kpi.value_dim AS value, aw_kpi.target_dim AS target, aw_kpi.status,
       aw_kpi.unit, aw_kpi.direction
FROM aw_kpi
GROUP BY aw_kpi.kpi, aw_kpi.member, aw_kpi.title, aw_kpi.folder,
         aw_kpi.value_dim, aw_kpi.target_dim, aw_kpi.status, aw_kpi.unit, aw_kpi.direction
