# Auditoría de medición auxiliar de gas — 2026-10-23

## Resultado

**233 pruebas Python PASS**, sin omitidas, en 164.049 segundos. Incluyen las 16
regresiones nuevas del adaptador y las pruebas existentes de exportación,
colecciones, PostgreSQL, coordinador y auditoría Termux. Las pruebas nuevas usan
el verificador Rust real y Polars; la integración con Blockscout se reproduce
desde respuestas retenidas. No hay dobles del verificador.

Las pruebas dirigidas cubren dos eventos en una misma transacción sin duplicar
el coste; identidades ajenas; solicitudes duplicadas; respuestas parciales;
hash/altura/fecha incompatibles; estados pendientes; comisiones inconsistentes;
flotantes/booleanos/overflow; cifras mayores que la precisión de JavaScript;
costes adicionales sin adaptador; journals alterados, incompletos o revocados;
ventanas sin contexto padre; enlaces simbólicos y sobrescritura.

La reproducción en un directorio temporal nuevo conserva exactamente los once
archivos generados, incluido el Parquet. `replay.json` registra esa comparación.
No son llamadas nuevas ni otra muestra. El journal original mantiene 17 registros,
tres liquidaciones y cuatro scopes completos. Sus bytes, owner y configuración
coinciden con el commit anterior y con las copias verificadas.

## Resultado público y límites

Seis respuestas públicas nuevas enriquecen los tres eventos ya retenidos.
Dos transacciones tienen presencia explícita en la lista parcial del bloque y
contabilidad consistente; suman **277470486732374 wei** de comisión de ejecución.
La tercera queda `membership_not_returned`, con coste `null`. Las respuestas de
bloque contienen 50 hashes y no prueban exhaustividad. El intento de completar
la pertenencia y los límites de la fuente están documentados en la evidencia.

No se asigna gas a cada evento ni se identifica al pagador de gas con quien
capturó el beneficio. No hay prueba criptográfica de inclusión de recibos, nuevos
logs canónicos, precios históricos, elegibilidad, pagos directos al constructor
ni resultado económico. Las prioridades cero observadas no rellenan esos campos.
No se habilita ninguna transición de ciclo de vida.

## Aislamiento, reproducción y pendientes

El verificador de aislamiento confirma 531 archivos fuente preservados,
106 workflows desactivados y cero activos. El delta está íntegramente bajo
`migration/nqc-miner/`; `scope.json` conserva el conteo exacto y cero archivos
del observador cambiados. `verification.json` fija hashes de fuentes, pruebas,
logs, entradas y salidas. El binario Rust permanece en SHA-256
`47292cd97732d246099b63f07cea6dc128dfd5612efe3341a6cefb4e631d4548`.

Rust no cambió y sus 155 pruebas históricas no se repitieron en este bloque.
No se ejecutó infraestructura productiva, un nuevo ensayo nativo PostgreSQL,
Shadow, Foundry, firmante ni canary. El avance global permanece **43/100**:
esta implementación parcial no cierra los 10 puntos de medición calibrada ni
ninguna salida operativa. Continúan abiertos los 57 puntos del plan.
