# Worker y auditoría de sync: verificación offline

Suite completa: 217 Python PASS. Después del último ajuste al auditor,
12 regresiones afectadas repetidas: PASS. El archivo de verificación liga fuentes,
logs, evidencia nativa e inputs sin cambios mediante SHA-256.

Las pruebas del worker usan Rust, Polars, filesystem y locks reales; RPC y SQL
están modelados. El experimento PostgreSQL nativo se audita separadamente, sin
volver a ejecutar sus programas adjuntos. No hay un worker real desplegado.

Ver `../../docs/AUDIT_WORKER_PREFLIGHT_20261022.md` y `../../docs/closure-plan.json`.
