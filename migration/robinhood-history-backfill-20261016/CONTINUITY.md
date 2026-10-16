# Continuidad NQC

Repositorio único: `josuechavando350-png/nexus-quant-capital`. Leer `AGENTS.md`.
PR12 es la base: `nqc/borrower-registry-20261016`, commit
`9dd86e13083c95a076793020635fc7d4fb3d5053`. Esta ampliación está en
`nqc/history-backfill-20261016`; buscar el PR más reciente antes de continuar.

Estado de este archivo al publicar el protocolo: pruebas offline y protocolo
previo; la captura real de este ensayo todavía no se ha ejecutado. No confundir
los mocks de las pruebas con evidencia de mercado. Se actualizará este archivo
al publicar el resultado, conservando el protocolo y sus hashes.

Cada ejecución horaria debe entregar un incremento acotado, probado y trazable.
Evitar trabajo simultáneo: revisar commits/PR recientes y no duplicar una captura
en curso. Si faltan herramientas o acceso, registrar el bloqueo y completar lo
posible offline. No afirmar continuidad ininterrumpida ni reparación del
programador cuando no exista una ejecución que permita observarlo.

Sin firmas, transacciones, operaciones con fondos, despliegues, suscripciones,
secretos, merge automático o cambios de workflows. Sin tocar nexus-engine,
Cano, aplicaciones cliente o dominios. Conservar el archivo original inmutable.

El siguiente paso después de este protocolo será publicar y auditar la captura
en `evidence/pilot`, comparar cobertura y tiempos, y decidir con esos datos si
conviene ampliar otro intervalo anterior o resolver la latencia primero.
Máximo por captura 512 métodos/900 segundos, sin reintentar una denegación ni
cambiar endpoint para evitarla. Las nuevas reglas de una nueva captura se
publican antes de observar sus resultados.
