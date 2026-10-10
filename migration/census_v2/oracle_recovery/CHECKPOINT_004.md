# Cuarto checkpoint: 25,000 bloques nuevos conciliados

Captura cerrada del **10 de octubre de 2026, 01:31:07.620059Z**. El trabajador
existente seguía `RUNNING`, con el mismo PID y lock; no se inició otro ni se
modificó su ritmo. El snapshot tenía 80 archivos cerrados y un contador de
80,170 bloques. Los **170 del archivo abierto no se copian ni cuentan**.

| Alcance | Resultado verificado |
| --- | --- |
| Delta después del checkpoint 003 | 25 archivos, 25,000 bloques y 1,675,000 precios nuevos |
| Prefijo completo de la continuación | 80,000 bloques y 5,360,000 precios; cero discrepancias con dRPC |
| Unión secundaria, sin duplicados | **85,170 / 215,036 bloques**, 5,706,390 coordenadas bloque/activo |
| Faltantes exactos | **129,866 bloques**, 25,965,486–26,095,351 |
| Eventos y recibos | El control integral vuelve a conciliar los 139 eventos y 127 recibos completos |

Los 55,000 bloques del prefijo previo se vuelven a verificar, sin contarlos como
nuevos. La unión previa de 5,170 bloques se reconstruye desde los chunks Nodies
y capturas piloto/parciales, conservando los 1,560 solapamientos. El plan de
continuación sigue siendo exactamente su complemento dentro del corte original.
No cambia el universo de 67 activos. **Todavía no se alcanza 10/20.**

## Bytes y reproducción

El ZIP delta contiene 34 archivos y tiene **8,825,372 bytes**, SHA-256
`c532e83a8fba3cc7c215cafa7e2a48fcad579f2bc02aa0494fcc4be60e12697e`.
Se conserva en tres partes binarias ordenadas; cada tamaño, SHA-256 y objeto
Git figura en `sequential-checkpoint-004-delta.parts.json`. Su concatenación
reproduce el ZIP exacto. El manifiesto interno fija cada miembro y el script
que hizo la copia, también incluido. No se vuelve a almacenar el prefijo de
55 archivos dentro de este delta.

El readback base procede del commit
`9269c9c93c286823c655866f021219e68a5570fe`, SHA-256
`80db84fc803e477bbbaa6761e2fdaa8c67a217dc42923d56370e2cb2f3b2b991`.
`prepare_checkpoint_four.py` comprueba archivo completo, partes, manifiesto,
fuente de captura, readback base, igualdad del prefijo y fuentes/anchors
compartidos. Rechaza corrupción, sustitución y duplicación antes de construir
una copia nueva. Este preparador no verifica precios; esa tarea pertenece al
consumidor de cobertura sin modificaciones.

Prepare primero `WORK/inputs` mediante las instrucciones de `COVERAGE_GATE.md`.
Después, desde este checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/prepare_checkpoint_four.py \
  --base "$WORK/inputs/closed-prefix" --out "$WORK/checkpoint004-prefix"
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/verify_coverage.py \
  --original "$WORK/inputs/original-oracle-evidence.zip" --d08 "$D08" \
  --pilot "$WORK/inputs/pilot-bundle/pilot" \
  --partial "$WORK/inputs/partial-bundle/remaining" \
  --checkpoint "$WORK/checkpoint004-prefix" --primary "$WORK/inputs/original/drpc" \
  --full-window "$WORK/inputs/full-window" --out "$WORK/checkpoint004-readback"
PYTHONDONTWRITEBYTECODE=1 NQC_COVERAGE_INPUTS="$WORK/inputs" NQC_ORACLE_D08="$D08" \
  NQC_ORACLE_CHECKPOINT_FOUR="$WORK/checkpoint004-prefix" \
  NQC_ORACLE_CHECKPOINT_FOUR_READBACK="$WORK/checkpoint004-readback" \
  python3 -m unittest discover -s migration/census_v2/oracle_recovery -p test_checkpoint_four.py -v
```

Las dos lecturas integrales locales producen cinco informes idénticos. Los
informes previos de oráculos y de eventos/recibos conservan sus hashes y se
referencian sin duplicar bytes. `checkpoint-004/report.json` fija sus identidades;
las salidas nuevas y pruebas quedan junto a él. El readback del prefijo tiene
SHA-256 `bada46df7f5f3fc4832b86cbba787d66a417d52f1a7be73bfe45feb906ff1f67`.
Una ejecución adicional sobre los chunks del servidor original produce ese
mismo readback byte por byte; su log se conserva. Esto comprueba paridad entre
entornos, sin convertirse en certificación independiente.
El informe integral tiene SHA-256
`410992a0fe18ec8936b726a692bef3b7a395b033ff2583e85e36e1166c98433d`.

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
abierto y 10/20, 15/20 y 20/20 permanecen pendientes.
