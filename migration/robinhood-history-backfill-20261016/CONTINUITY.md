# Continuidad NQC

Repositorio único: `josuechavando350-png/nexus-quant-capital`. Leer `AGENTS.md`.
PR12 es la base: `nqc/borrower-registry-20261016`, commit
`9dd86e13083c95a076793020635fc7d4fb3d5053`. Esta ampliación está en
`nqc/history-backfill-20261016`; buscar el PR más reciente antes de continuar.

Estado actualizado: captura completada 2026-10-16, 06:42:58–06:51:31 UTC.
Protocolo público previo `ba730e532ce93c983f5aa09c65a4a54fa6957c5b`, tree
`baada1be75a72134a0792855be4937b6494f92af`. Los 19 archivos registrados siguen
idénticos. Leer `README.md`, `evidence/pilot-summary.json` y
`evidence/provenance.json`. El commit de resultados es el HEAD publicado de la
rama `nqc/history-backfill-20261016`; contrastarlo con el PR y no usar un SHA
escrito por anticipado como si fuera un commit existente.

Resultado: 831,201 bloques contiguos (89,046,281–89,877,481), 84 tramos,
38 Borrow, 23 cuentas, 19 con deuda; 16.8041891461% de borrowShares cubiertas,
83.1958108539% sin cubrir. Las trece cuentas nuevas añaden 6.6615791202 puntos
de cobertura en los mismos bloques. Cero señales y cero posiciones no saludables
en tres bloques; no inferir ausencia de oportunidades en el universo omitido.
Lectura nueva 2.974/3.348/3.074 s vs batch 23.796/23.203/26.933 s, con igualdad
exacta. Sigue sin alcanzar el presupuesto supuesto de 1 s y excluye el chequeo
canónico posterior. Sin rutas, ingresos, financiación ni envíos de transacciones.
256 métodos/176 HTTP/cero errores, 512.82 s. 72 pruebas Python y 11 Solidity
aprobadas. Los 377 blobs originales y workflows deshabilitados se conservaron.

Cada ejecución horaria debe entregar un incremento acotado, probado y trazable.
Evitar trabajo simultáneo: revisar commits/PR recientes y no duplicar una captura
en curso. Si faltan herramientas o acceso, registrar el bloqueo y completar lo
posible offline. No afirmar continuidad ininterrumpida ni reparación del
programador cuando no exista una ejecución que permita observarlo.

Sin firmas, transacciones, operaciones con fondos, despliegues, suscripciones,
secretos, merge automático o cambios de workflows. Sin tocar nexus-engine,
Cano, aplicaciones cliente o dominios. Conservar el archivo original inmutable.

## Próximo incremento concreto

1. Recuperar el último HEAD real y verificar el manifiesto, las fuentes y el
   registro final antes de usarlo. Fuente nueva:
   `migration/robinhood-history-backfill-20261016/evidence/pilot/registry.json`,
   raíz SHA-256 `3659ce75ace86563b3a3c6ddbed5382b98566db332c5fc57116c7885308a70f4`.
   No volver al registro de PR12 ni repetir los 400,000 bloques ya ampliados.
2. Preparar un ensayo nuevo de los 400,000 bloques inmediatamente anteriores:
   **88,646,281–89,046,280**. Preservar la fuente, revalidar ambos checkpoints,
   unir sin huecos y cerrar la cola hasta una cabecera actual menos 64. Selección
   independiente de salud/resultados, todas las cuentas, sin recortar excedentes.
   Publicar código/política/hashes antes de la nueva captura. El runner actual
   fija su política: no editar retroactivamente sus archivos registrados.
3. Reutilizar la lectura única ya comprobada para reconciliar la cohorte nueva,
   bajo un protocolo nuevo. No gastar otra vez tres repeticiones batch si no hay
   una hipótesis nueva de comparación. Si aparecen candidatos, guardar la regla
   de selección y medir en un ensayo prospectivo la ruta y su supervivencia;
   ningún candidato equivale por sí mismo a beneficio.
4. Trabajo posterior de latencia: comparar transporte con conexión persistente
   contra el actual en condiciones y orden fijados, sin asumir de antemano que
   sea más rápido ni confundir una lectura con el ciclo completo de decisión.
   Falta medir el tiempo hasta terminar también validación/simulación.

El auditor prueba reconstrucción de ejecuciones completas y un rechazo de la
lectura nueva. Antes de generalizarlo, ampliar pruebas de paradas tempranas,
incluido fallo justo después de unir historia y antes de iniciar catch-up: su
selección del archivo persistido requiere revisión en ese punto. Un error del
auditor no permite descartar respuestas crudas o presentar el ensayo como éxito.

## Comandos y herramientas

Python usa únicamente la biblioteca estándar. Prueba y auditoría offline:

```bash
python -m unittest discover -s migration/robinhood-history-backfill-20261016 -p 'test_experiment.py' -v
python migration/robinhood-history-backfill-20261016/audit_experiment.py migration/robinhood-history-backfill-20261016/evidence/pilot --out /tmp/nqc-audit.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

En el entorno de esta captura solc estaba en
`/tmp/nqc-robinhood-work/bin/solc-0.8.23` y Foundry en
`/workspace/scratch/08b0192684a7/foundry-bin`. Son rutas temporales, no dependencias
garantizadas para otro turno. `build_lens.py` verifica los bytes de compilación;
el lector puede verificar el artefacto existente sin volver a compilarlo.
El endpoint fijo está en el lector heredado y en las fuentes oficiales del
protocolo. No volver a probar endpoints previamente denegados ni el conector de
explorador con cuota agotada. Si falta una capacidad, registrar el bloqueo real.

GitHub: las herramientas de árbol/commit/rama/PR permitieron publicar; `git fetch`
funcionó. El push por CLI no tenía autenticación. Tras publicar, se contrastaron
árbol y padres remotos antes de alinear la rama local. No incluir archivos de
caché, claves o rutas de otros proyectos. Mantener el PR borrador y sin fusionar.

Máximo por captura 512 métodos/900 segundos, sin reintentar una denegación ni
cambiar endpoint para evitarla. Las nuevas reglas de una nueva captura se
publican antes de observar sus resultados.
