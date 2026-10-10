# Cobertura histórica de precios completa; Census sigue abierto

La continuación Ethereum terminó a las **2026-10-10T05:30:23.188910Z**.
Se conservaron `progress.json` y `acquisition.json` idénticos y los 210 archivos
cerrados: 209 archivos de 1,000 bloques y uno final de 866. El proceso original
terminó y liberó su lock. No fue reiniciado, duplicado ni acelerado.

| Alcance verificado | Resultado |
| --- | --- |
| Ventana Ethereum | 25,880,316–26,095,351; 215,036 bloques |
| Activos al oráculo | 67 |
| Unión secundaria exacta | 215,036 / 215,036 bloques |
| Coordenadas bloque/activo conciliadas | 14,407,412 |
| Bloques faltantes / precios discrepantes | 0 / 0 |
| Nuevo delta respecto al checkpoint 006 | 44,866 bloques / 3,006,022 precios |
| Continuación completa | 209,866 bloques / 14,061,022 precios |
| Unión previa preservada | 5,170 bloques; 1,560 solapamientos previos no se duplican |
| Eventos / recibos completos conciliados | 139 / 127 |
| Capturas abiertas excluidas | 0; adquisición terminal |

La verificación integral reproduce las cinco salidas dos veces localmente,
con bytes iguales. El servidor original reproduce el mismo readback de la
continuación, comparado byte por byte. Se comprueban los chunks dRPC originales,
las respuestas Nodies, calldata, blockHash, canonicalidad solicitada, fuentes,
recepción actual, cronología, prefijo anterior y partición exacta. Los informes
están en `checkpoint-007/`. El consumidor de precios/integración no cambió.

## Archivo exacto y fuentes

ZIP delta: **15,988,434 bytes**, **55 miembros**, SHA-256
`673871b6f0dab9af61d66cca361aab50e3fc2d2264a02ba5d03360070fe82039`.
Se conserva en seis partes ordenadas, cinco de 3,000,000 bytes y una de 988,434,
con bytes, SHA-256 y Git blobs en `sequential-checkpoint-007-delta.parts.json`.

Base del delta: checkpoint 006 publicado en
`3c8e9117f09ea3c6a076ab57e30642f8a165a0fe`. Readback base:
`d1211693d2e2a1f3df589b2d163a88733aceb535e50f023cf62cef2979137527`.
Productor original de captura:
`c163b876d3310855f1db45bfc3ab4189b24d865b`; su identidad se conserva aunque
el snapshot, consumidor y publicación sean posteriores.

Readback terminal de continuación:
`ebb2274e3568b85a830973f9a8dc72a848fffe1d08c1619b7138d2c5c78fd7c5`.
Informe integral:
`890260d0107ec89bc66829c390c38719b895ce15b02236a88989826e37f1f408`.

## Validación y fallo conservado

Pasan **12 controles reales/adversariales** del checkpoint y **9 de aislamiento**,
cero fallos u omisiones en esas suites. Los controles rechazan discrepancia entre
terminales, contador inflado, fallo borrado, estado RUNNING, padding del último
archivo, captura dañada, duplicados y sustitución de fuente/base/transporte.
La verificación conserva los 637 objetos originales y cero workflows activos.
Rust/Solidity no cambiaron y sus suites no se repitieron.

El primer script de snapshot creó su ZIP pero falló al imprimir el tamaño:
usó `st_size()` en vez de `st_size`. La fuente y traceback se retienen en
`checkpoint-007/attempt-001-*`; la corrección se ejecutó en un directorio nuevo.
El ZIP del primer intento permanece en el servidor, con SHA-256
`f407a693afcafd14aa71855cd2621d28d19aa36d124ad6ab27d0c94c4c1f93de` y
15,988,437 bytes; ese ZIP no se presenta como el archivo publicado. Ningún
fallo de adquisición se borró y no se rehicieron solicitudes RPC para corregir
el empaquetado. El 429 histórico anterior también permanece en el readback.

## Reproducción

Prepare los insumos originales según `COVERAGE_GATE.md` y el prefijo 006 según
`CHECKPOINT_006.md`. Use rutas de salida nuevas:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/prepare_checkpoint_seven.py \
  --base "$WORK/checkpoint006-prefix" --out "$WORK/checkpoint007-prefix"
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/verify_coverage.py \
  --original "$WORK/inputs/original-oracle-evidence.zip" --d08 "$D08" \
  --pilot "$WORK/inputs/pilot-bundle/pilot" --partial "$WORK/inputs/partial-bundle/remaining" \
  --checkpoint "$WORK/checkpoint007-prefix" --primary "$WORK/inputs/original/drpc" \
  --full-window "$WORK/inputs/full-window" --out "$WORK/readback007"
PYTHONDONTWRITEBYTECODE=1 NQC_COVERAGE_INPUTS="$WORK/inputs" NQC_ORACLE_D08="$D08" \
  NQC_ORACLE_CHECKPOINT_SIX="$WORK/checkpoint006-prefix" \
  NQC_ORACLE_CHECKPOINT_SEVEN="$WORK/checkpoint007-prefix" \
  NQC_ORACLE_CHECKPOINT_SEVEN_READBACK="$WORK/readback007" \
  python3 -m unittest discover -s migration/census_v2/oracle_recovery -p test_checkpoint_seven.py -v
```

## Límites que permanecen

Esto completa el cruce histórico de precios por dos operadores nombrados, no
prueba independencia de sus nodos, headers completos, frescura por candidato,
preestado de cada transacción ni observación original de Nexus. Tampoco resuelve
compatibilidad, principal/gas admisible, rutas monetizables, costes completos,
competencia/captura, los cuatro ZIPs físicos sin bytes o aceptación independiente.
No hay P&L admitido ni cierre de Census. La expansión Base tiene su propia
evidencia y bloqueo de acceso en `../base_expansion/README.md`.
