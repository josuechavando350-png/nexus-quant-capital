# Rutas V2 entre activos de Aave: cruce íntegro del inventario retenido

Este consumidor offline autentica el ZIP D08 original y recorre sus 523,424
pools V2 y 67 reservas Aave en el bloque Ethereum 26,095,351. Conserva el
productor original, hashes de miembros, identidades e índices completos. Cruza
el inventario con los 474 pares D12 de 400 borrowers sin cambiar las fuentes.
El head de entrada es `3c8e9117f09ea3c6a076ab57e30642f8a165a0fe`.

## Qué se midió

| Partición disjunta de los pools | Cantidad |
| --- | ---: |
| Rechazados en reconstrucción de estado | 728 |
| Estado admitido pero liquidez etiquetada cero | 19,193 |
| Estado admitido y reservas positivas, ningún extremo Aave | 6,016 |
| Estado admitido y reservas positivas, un extremo Aave | 497,385 |
| Estado admitido y reservas positivas, ambos extremos Aave | 102 |
| Total | 523,424 |

Los 19,193 son posteriores al filtro de estado, no sustituyen los 19,449
`ZERO_LIQUIDITY_NOT_ROUTABLE` originales. Las particiones usan filtros distintos.
Se autentican tanto los miembros de mercado como la admisión de tokens; no se
admiten pools duplicados por dirección, identidad, índice o par canónico.

De los 67 activos, 43 tienen al menos un pool V2 vecino seleccionado. Se
enumeran las 4,422 conversiones dirigidas entre activos distintos: 1,222
tienen una conexión directa o de dos swaps y 3,200 no la tienen en este
ámbito. Hay 204 conversiones con conexión directa y 1,214 con dos swaps;
esas categorías se solapan y no se suman. Las rutas de ida y vuelta son
conversiones distintas, no ganancias independientes.

`routes.jsonl.gz` contiene todas las conversiones, conteos, compromiso del
conjunto íntegro de intermediarios y ejemplos deterministas (ruta directa y
hasta tres intermediarios). Cada ejemplo fija direcciones de pools, índices,
activos, reservas enteras y fee de swap declarado. Los ejemplos se eligen por
orden de dirección, sin ranking de rentabilidad. Los intermediarios completos
se reconstruyen desde D08; su hash detecta cambios o pérdidas de miembros.

## Efecto sobre los candidatos existentes

| Clasificación original preservada | Ruta directa/dos swaps presente | Sin esa ruta V2 en este corte | Mismo activo, sin swap colateral-deuda | Total |
| --- | ---: | ---: | ---: | ---: |
| Evidencia insuficiente | 366 | 50 | 16 | 432 |
| No ejecutable por el protocolo en ese estado | 34 | 1 | 7 | 42 |
| Total | 400 | 51 | 23 | 474 |

La nueva observación precisa dónde buscar ejecución y qué pares necesitan
otros pools, más saltos o mecanismos de salida. No reclasifica los 50 pares
insuficientes sin ruta corta como imposibles globalmente. Tampoco elimina los
rechazos del protocolo por encontrarles un camino de intercambio.

`assets.jsonl` conserva los 67 testimonios de compatibilidad por rol del
productor original, todos `BLOCKED`, e incidencia de cada activo en D12.
`d12-routing-overlay.jsonl` enlaza los 474 pares con esta observación y conserva
razones/clasificaciones. La incidencia por activo no se suma como pares únicos.
Los activos requeridos pueden aparecer en el papel de deuda y de colateral.

## Límites económicos

Una conexión con reservas positivas no prueba tamaño ejecutable, comportamiento
de transferencia, compatibilidad del intermediario, precio, repayment, gas,
inclusión o beneficio. Aquí no se calculan cotizaciones o P&L condicionales.
Las reservas pertenecen a un único ancla, no al preestado de los ganadores ni
a todas las fechas del histórico. El alcance omite otros DEX/factories,
liquidez concentrada, conversiones de wrappers y rutas de más de dos swaps.

Este análisis no mide arbitraje de todo el inventario ni oportunidades de L2/L3.
Su ausencia de ruta es local al ámbito definido. Sigue habiendo 432 pares con
evidencia insuficiente y 42 rechazos previos. El valor ejecutable admitido
permanece en cero; el P&L completo permanece desconocido. No hay certificación
independiente, adquisición nueva, gasto, firma, transmisión o despliegue.

## Reproducción y controles

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/audit_routing_topology.py \
  --d08 "$D08" --out "$WORK/routing-readback"
TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 NQC_ORACLE_D08="$D08" \
  NQC_ROUTING_READBACK="$WORK/routing-readback" \
  python3 -m unittest discover -s migration/census_v2 -p test_routing_topology.py -v
```

Pasan once pruebas, incluidas dos ejecuciones completas con cuatro salidas
idénticas y casos adversariales de identidad, duplicación, reservas cero,
pertenencia a factory, promoción económica falsa y rechazo global indebido.
Los nueve controles de aislamiento pasan; 637 objetos originales se autentican
y cero workflows están activos. Rust/Solidity no cambian y no se repiten.
Los resultados, manifiesto y logs quedan en `evidence/routing-topology/`.
