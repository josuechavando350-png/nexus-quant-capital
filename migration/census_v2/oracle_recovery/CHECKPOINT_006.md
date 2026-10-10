# Sexto checkpoint: 26,000 bloques nuevos conciliados

Snapshot del **10 de octubre de 2026, 04:07:42.209564Z**. El recolector original
conserva proceso, lock y ritmo. Tenía 165 archivos cerrados y 165,280 capturas;
los **280 registros del archivo abierto quedan excluidos**. No se inició otro
recolector ni se hicieron peticiones RPC desde el snapshot o su verificación.

| Alcance | Resultado |
| --- | --- |
| Delta posterior al checkpoint 005 | 26 archivos, 26,000 bloques y 1,742,000 precios nuevos |
| Prefijo completo de continuación | 165,000 bloques, 11,055,000 precios; cero discrepancias con dRPC |
| Unión secundaria sin duplicados | **170,170 de 215,036 bloques**, 11,401,390 coordenadas bloque/activo |
| Faltantes exactos | **44,866 bloques**, 26,050,486 a 26,095,351 |
| Eventos y recibos | Los 139 eventos y 127 recibos completos vuelven a conciliar |

Los 139,000 bloques anteriores se verifican de nuevo y no se suman como nuevos.
La unión previa de 5,170 bloques se reconstruye desde las fuentes originales;
los 1,560 solapamientos se excluyen del doble conteo. El universo conserva 67
activos. Las dos ejecuciones locales producen cinco informes idénticos; el
readback completo del prefijo en el servidor original coincide byte por byte.

## Compromisos y reproducción

El ZIP tiene **9,138,413 bytes**, 35 miembros y SHA-256
`1a0feec1ba7953e45887f5ca393c30e012ad6bc147818c05035b053679e5a6c1`.
Está conservado en cuatro partes binarias ordenadas de 3,000,000, 3,000,000,
3,000,000 y 138,413 bytes. `sequential-checkpoint-006-delta.parts.json` fija
tamaños, SHA-256 y objetos Git. Su concatenación reconstruye el ZIP exacto.
El manifiesto interno autentica todos los miembros y el script del snapshot.

Base publicada: commit `91b7108c5b56c768127bd9b73202d5156635ec18`, readback
`7b3310a04f198d2b3bd170b0d3d04e9621a25be0f6a88d8f5e5992402cfe5d26`.
El nuevo preparador autentica partes, archivo completo, miembros, fuente,
readback base, prefijo cerrado y fuentes compartidas. El consumidor original
sin modificaciones verifica todos los vectores de precios y la unión exacta.

Prepare `WORK/inputs` siguiendo `COVERAGE_GATE.md` y el prefijo del checkpoint
005 siguiendo `CHECKPOINT_005.md`. Use directorios de salida nuevos:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/prepare_checkpoint_six.py \
  --base "$WORK/checkpoint005-prefix" --out "$WORK/checkpoint006-prefix"
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/verify_coverage.py \
  --original "$WORK/inputs/original-oracle-evidence.zip" --d08 "$D08" \
  --pilot "$WORK/inputs/pilot-bundle/pilot" \
  --partial "$WORK/inputs/partial-bundle/remaining" \
  --checkpoint "$WORK/checkpoint006-prefix" --primary "$WORK/inputs/original/drpc" \
  --full-window "$WORK/inputs/full-window" --out "$WORK/checkpoint006-readback"
TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 NQC_COVERAGE_INPUTS="$WORK/inputs" \
  NQC_ORACLE_D08="$D08" NQC_ORACLE_CHECKPOINT_FIVE="$WORK/checkpoint005-prefix" \
  NQC_ORACLE_CHECKPOINT_SIX="$WORK/checkpoint006-prefix" \
  NQC_ORACLE_CHECKPOINT_SIX_READBACK="$WORK/checkpoint006-readback" \
  python3 -m unittest discover -s migration/census_v2/oracle_recovery -p test_checkpoint_six.py -v
```

Readback de continuación:
`d1211693d2e2a1f3df589b2d163a88733aceb535e50f023cf62cef2979137527`.
Informe integral:
`42c1a322e7c4f8d357e86917efa57679c575045453194791f37b5af6d29b4c46`.
Los informes previos de oráculos y eventos/recibos mantienen sus hashes; se
referencian sin duplicar bytes. Los tres informes nuevos, logs y validación
están en `checkpoint-006/`.

Pasan ocho pruebas reales/adversariales y nueve de aislamiento, sin fallos ni
omisiones. El verificador autentica los 637 objetos originales: 531 fuentes y
106 workflows desactivados; cero activos. Rust/Solidity no cambian y no se
repiten. El trabajo local utiliza una copia aislada con espacio temporal en RAM.

## Límites preservados

La cobertura sigue incompleta. Las horas de recepción son actuales; no prueban
conocimiento histórico de Nexus. Dos operadores no autentican independencia
de nodos subyacentes. Este checkpoint no acredita financiación operativa,
compatibilidad, captura, costes completos o P&L, ni aceptación independiente.
Los cuatro ZIPs físicos con 403 siguen sin bytes. No hubo gasto, transacción,
despliegue ni ampliación de permisos. Census permanece abierto y no se emiten
puntuaciones de avance.
