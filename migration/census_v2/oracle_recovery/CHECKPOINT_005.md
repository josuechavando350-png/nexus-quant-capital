# Quinto checkpoint: 59,000 bloques nuevos conciliados

Captura cerrada del **10 de octubre de 2026, 03:21:01.448325Z**. El trabajador
existente seguía `RUNNING`, con el mismo PID y lock; no se inició otro ni se
modificó su ritmo. El snapshot tenía 139 archivos cerrados y un contador de
139,920 bloques. Los **920 del archivo abierto no se copian ni cuentan**.

| Alcance | Resultado verificado |
| --- | --- |
| Delta después del checkpoint 004 | 59 archivos, 59,000 bloques y 3,953,000 precios nuevos |
| Prefijo completo de la continuación | 139,000 bloques y 9,313,000 precios; cero discrepancias con dRPC |
| Unión secundaria, sin duplicados | **144,170 / 215,036 bloques**, 9,659,390 coordenadas bloque/activo |
| Faltantes exactos | **70,866 bloques**, 26,024,486–26,095,351 |
| Eventos y recibos | El control integral vuelve a conciliar los 139 eventos y 127 recibos completos |

Los 80,000 bloques del prefijo previo se vuelven a verificar, sin contarlos como
nuevos. La unión previa de 5,170 bloques se reconstruye desde los chunks Nodies
y capturas piloto/parciales, conservando los 1,560 solapamientos. El plan de
continuación sigue siendo exactamente su complemento dentro del corte original.
No cambia el universo de 67 activos. **La cobertura histórica sigue incompleta.**

## Bytes y reproducción

El ZIP delta contiene 68 archivos y tiene **20,935,131 bytes**, SHA-256
`be2b776a3aa55c70f72c75a7ce2c36496aa698567b6ef23dd260b451e43b4758`.
Se conserva en siete partes binarias ordenadas; cada tamaño, SHA-256 y objeto
Git figura en `sequential-checkpoint-005-delta.parts.json`. Su concatenación
reproduce el ZIP exacto. El manifiesto interno fija cada miembro y el script
que hizo la copia, también incluido. No se vuelve a almacenar el prefijo de
80 archivos dentro de este delta.

El readback base procede del commit
`a13e195b909cc55062ff2406a29a2a7f15f43867`, SHA-256
`bada46df7f5f3fc4832b86cbba787d66a417d52f1a7be73bfe45feb906ff1f67`.
`prepare_checkpoint_five.py` comprueba archivo completo, partes, manifiesto,
fuente de captura, readback base, igualdad del prefijo y fuentes/anchors
compartidos. Rechaza corrupción, sustitución y duplicación antes de construir
una copia nueva. Este preparador no verifica precios; esa tarea pertenece al
consumidor de cobertura sin modificaciones.

Prepare primero `WORK/inputs` mediante `COVERAGE_GATE.md` y el prefijo
`WORK/checkpoint004-prefix` mediante `CHECKPOINT_004.md`. Después, desde este checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/prepare_checkpoint_five.py \
  --base "$WORK/checkpoint004-prefix" --out "$WORK/checkpoint005-prefix"
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/verify_coverage.py \
  --original "$WORK/inputs/original-oracle-evidence.zip" --d08 "$D08" \
  --pilot "$WORK/inputs/pilot-bundle/pilot" \
  --partial "$WORK/inputs/partial-bundle/remaining" \
  --checkpoint "$WORK/checkpoint005-prefix" --primary "$WORK/inputs/original/drpc" \
  --full-window "$WORK/inputs/full-window" --out "$WORK/checkpoint005-readback"
PYTHONDONTWRITEBYTECODE=1 NQC_COVERAGE_INPUTS="$WORK/inputs" NQC_ORACLE_D08="$D08" \
  NQC_ORACLE_CHECKPOINT_FOUR="$WORK/checkpoint004-prefix" \
  NQC_ORACLE_CHECKPOINT_FIVE="$WORK/checkpoint005-prefix" \
  NQC_ORACLE_CHECKPOINT_FIVE_READBACK="$WORK/checkpoint005-readback" \
  python3 -m unittest discover -s migration/census_v2/oracle_recovery -p test_checkpoint_five.py -v
```

Las dos lecturas integrales locales producen cinco informes idénticos. Los
informes previos de oráculos y de eventos/recibos conservan sus hashes y se
referencian sin duplicar bytes. `checkpoint-005/report.json` fija sus identidades;
las salidas nuevas y pruebas quedan junto a él. El readback del prefijo tiene
SHA-256 `7b3310a04f198d2b3bd170b0d3d04e9621a25be0f6a88d8f5e5992402cfe5d26`.
Una ejecución adicional sobre los chunks del servidor original produce ese
mismo readback byte por byte; su log se conserva. Esto comprueba paridad entre
entornos, sin convertirse en certificación independiente.
El informe integral tiene SHA-256
`8cde72512929d269125d1a10dee1a1f597730147017995e075c4fa91381cc677`.

Pasan ocho pruebas reales/adversariales nuevas y nueve de aislamiento. Los
637 objetos originales permanecen intactos y hay cero workflows activos.
Las pruebas Rust/Solidity no se repiten porque esas fuentes no cambiaron.
El trabajo local usa espacio temporal en memoria para evitar el disco agotado;
no se borran fuentes ni se modifica una aserción por conveniencia.

Las respuestas cerradas conservan sus horas de recepción actuales, no tiempos
históricos de observación de Nexus. Ni los nombres de dos operadores prueban
nodos subyacentes independientes, ni este checkpoint certifica ejecución,
financiación, captura o P&L. El 429 previo y los cuatro ZIPs físicos con 403
siguen preservados; estos últimos continúan sin bytes. No hubo gas, firma,
transmisión, despliegue, servicio nuevo ni ampliación de permisos. Census sigue
abierto. Por petición posterior del usuario se suspenden los avisos de puntuación;
los criterios técnicos de cobertura y cierre permanecen vigentes.
