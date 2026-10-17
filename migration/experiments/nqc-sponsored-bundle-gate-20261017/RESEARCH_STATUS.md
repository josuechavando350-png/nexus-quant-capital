# Continuidad — Directiva 004

Rama `research/nqc-sponsored-bundle-gate-20261017`; base `937a833a481fd69d2ce96152deb7d4d0760d6596`. El commit que contiene este documento se obtiene con `git rev-parse HEAD`; los commits publicados y su read-back se registran en `PUBLICATION.md`, evitando un hash autorreferencial.

Última verificación: 2026-10-17, 27 escenarios con 149 recibos locales; 4 controles de pool; 2 exclusiones de candidatos. 14 pruebas de evidencia, 168 Python de regresión, 50 Solidity (33+17), 9 aislamiento y verificador aprobados. Estos grupos se ejecutaron durante esta directiva; no se suman repeticiones. Logs completos en evidence/. Fallos de desarrollo preservados y corregidos: aislamiento de candidatos en el pool y una expectativa incorrecta sobre el orden por prioridad. Las reversiones financieras esperadas siguen siendo negativas.

Funciona: compilación original y paridad con 003 corregida, seis transacciones C1 en un bloque, retorno U real local, C2 primer ciclo con préstamo flash, reconciliación independiente de traces/logs frente a diffs de almacenamiento, criterio de participación del financiador y fronteras exactas condicionadas.

Resultados: C1 y C2 tienen igual output/residual en el estado controlado; C1 cuesta menos en primer ciclo y no necesita cash flash. C2 requiere 8 WETH, y su liquidación aislada es más barata. C1 a 21 gwei pierde dinero para el financiador y se rechaza, aun con WETH positivo NQC. Ninguna variante acredita aceptación comercial.

Pendientes: C1 predesplegado comparable; validación de ramas Lido/wrapper ajenas a la ruta WETH; estado auténtico B/Fluid; financiación externa identificada y sin recurso; captura; frecuencia de oportunidades económicamente admisibles. No hay nuevo testigo histórico ni candidato promovido. Costos comerciales indispensables permanecen UNKNOWN.

Próxima prueba decisiva y criterio: replay histórico exacto B solo cuando exista testigo gratuito permitido. Deben verificarse estado padre, aplicación de tx0, posición/oráculo/IRM, estado Fluid, conversión ejecutable, todos los repagos y balances; un recibo exitoso o excedente teórico no basta. Archivos de continuidad: DIRECTOR_HANDOFF.md, SOURCE_LOCK.json, economics.py, run_coordinated.py y los bloqueos históricos preservados en Directiva 003.

Decisión actual PAUSAR escalada; gasto $0 MXN; ganancias NQC certificadas US$0; mensual NO ESTIMABLE. Todos los procesos Anvil usados son hijos finitos terminados al salir; no se dejó observación persistente.
