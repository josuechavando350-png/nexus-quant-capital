# Auditoría de estados históricos Aave — 2026-10-23 UTC

## Resultado del software

**167 pruebas Rust y 242 Python aprobadas**, sin fallos ni omitidas en la corrida
final. Clippy con `-D warnings`, formato, aislamiento y correspondencia entre
fuentes y build también pasan. Los logs y hashes completos están en
`evidence/aave-state-audit-20261023/summary.json`.

Las 11 pruebas nuevas del lector cubren series no monótonas, censura, deuda cero,
umbral exacto, cambios de oráculo/unidades, resultados ABI inválidos, falta de
archivo, desacuerdo, reorganizaciones interiores y de anclajes, padres,
timestamps iguales en L2, cadenas/proveedores ajenos, límites, Shadow y llamadas
no permitidas. Una prueba adicional ejecuta el getter fijado a hash mediante
el transporte HTTP real contra un servidor local. Las ocho pruebas Python del
preparador usan Rust y Polars reales, con corrupción, revocación, identidad,
reproducción y preservación de fuentes.

La primera corrida queda retenida en `aave-state-preflight-20261023`: 167 Rust
aprobadas y una comparación histórica fallida entre las 241 pruebas Python.
El constructor incorporó correctamente la nueva identidad del verificador,
pero el test exigía igualdad con un paquete construido con el ejecutable viejo.
Se separaron la reproducción con el mismo verificador y la conservación de la
entrega histórica. La prueba añadida comprueba ambas identidades y el hash del
runner que realmente se ejecutó en Termux. No se regeneró ese runner ni se
cambió evidencia PostgreSQL anterior.

## Lectura pública y auditoría de datos

Se consultaron PublicNode y dRPC mediante sus endpoints públicos, primero un
estado acotado y después los 16 bloques previos a cada uno de los tres eventos
Aave ya conservados. Los tres intervalos finalizaron con acuerdo entre ambos
proveedores y revalidación de todos los hashes. No son tres liquidaciones nuevas.

| Evento en bloque | Intervalo previo | Salud en el último cierre, escala 10¹⁸ | Episodio de salud < 1 |
| --- | --- | --- | --- |
| 26248076 | 26248060–26248075 | 1000234567630119811 | Ninguno observado |
| 26248114 | 26248098–26248113 | 999999987794950345 | Bloque 26248113; límite derecho censurado |
| 26248379 | 26248363–26248378 | 1000521727527941698 | Ninguno observado |

Son **48 estados históricos distintos**, 336 getters acordados y 672 respuestas
de proveedores. La prueba inicial de un bloque repite el último estado del
primer intervalo y no incrementa esos conteos. En los tres intervalos se
conservaron dos precios por estado, con unidad base `100000000` y moneda base
cero según la interfaz. Los precios, direcciones, llamadas y respuestas
completas permanecen en los JSON originales.

`public-read-audit.json` registra la auditoría offline: reproduce ambos lotes
de planes y sus exports byte por byte; vuelve a verificar el journal original
con Rust; comprueba owner, configuración, build, evento y hashes de archivos;
decodifica de forma independiente cada respuesta ABI; y vuelve a calcular
precios, salud, episodios, continuidad y cambios de oráculo. El auditor rechaza
18 mutaciones de identidad, parámetros, respuestas y resultados calculados.

El journal original conserva exactamente sus 17 registros, tres eventos y
cuatro scopes completos. Las respuestas nuevas enriquecen esa muestra. No hay
prueba criptográfica de estado, certificación de proxy/implementación,
independencia acreditada de proveedores ni garantía de frescura del oráculo.

Dos posiciones aún tenían salud por encima de uno en B−1. Eso no contradice
las liquidaciones observadas en B: falta reconstruir lo ocurrido dentro del
bloque y las reglas ejecutables. No se ha inferido elegibilidad ni latencia de
liquidación. Tampoco se ha convertido el valor de oráculo en beneficio realizado.

## Reproducción, aislamiento y estado

El ejecutable de la lectura y de las pruebas corresponde a
`cc4abee3fb4bc2438057e5bbcfd35145f7ebc1f1`, SHA-256
`b199f60e13d64e39dd8b66f2f5cf32e63fa6df2d1a9f27d54a1339cb992a7af0`.
`source-history.bundle` conserva ese commit y sus ancestros locales posteriores
a `16e352225ba8a6a931834c4edf3d86d9a2924b7d`; `git bundle verify` pasa.
Los cambios posteriores de este bloque son pruebas Python, documentación y
evidencia, registrados por separado en el manifiesto final. Un build desde otro
commit tendrá una identidad distinta y exige una configuración nueva.

El aislamiento conserva 531 archivos fuente, 106 workflows desactivados y cero
activos. Todo el delta está bajo `migration/nqc-miner/`. No se cambia el
observador, no se inicia infraestructura compartida y no se firma ni se emite
ninguna transacción.

**Avance global: 43/100.** El bloque proporciona lecturas históricas reales y
auditadas, pero no cierra medición calibrada en varias cadenas, reconstrucción
causal de ejecución, operación sostenida ni ninguna salida de fase. Los 57
puntos pendientes conservan sus criterios en `docs/closure-plan.json`.
