# NQC666 R3 — verificación de estado antes del cálculo

**Resultado:** implementado y probado un ingreso offline con pruebas de cuenta,
código y almacenamiento, invalidación de snapshots y conexión condicional al
evaluador Rust R1. Reutilizar nodos dentro de cada paquete reduce la mediana de
verificación **19,3%**, conservando los resultados y rechazos del corpus. Se conserva
una regresión del máximo; no se declara un sistema listo para operar.

Trabajo ejecutado el **18 de octubre de 2026**, hora de Ciudad de México.
Medición: 2026-10-19 00:15:14–00:17:39 UTC. Rama experimental
`research/nqc-666-third-eye-20261018`, sobre R2
`43e1761caec3d45dedd08c177b51f97e066fe075`. Solo se añade este directorio.

## Implementado

- Verificación del hash de un encabezado fijado y pruebas EIP-1186 para la cuenta,
  código y nueve slots necesarios para posición/mercado/parámetros.
- Parsing acotado, rechazo de ambigüedad, metadata discrepante, pruebas faltantes,
  slots incorrectos, inconsistencias económicas básicas y datos obsoletos.
- Identidad de mercado reconstruida, datos de origen preservados y salida inmutable.
- Caché de decodificación estrictamente local a cada paquete, con control equivalente
  sin caché. Cada prueba sigue comprobándose contra su raíz y clave.
- Gateway de un hilo con invalidación previa al procesamiento, épocas y tickets.
  El fallo no conserva una oportunidad anterior; un reset invalida todos los tickets.
- Escenarios de deuda/capacidad mediante el ejecutable Rust R1 sin modificarlo.
  Precio supuesto identificado como tal; acumulación de intereses desconocida bloquea
  el cálculo. Elegibilidad observada y autorización comercial continúan deshabilitadas.

No se añadieron servicios externos, concurrencia de búsqueda ni dependencias instaladas.
Python reutiliza las bibliotecas criptográficas que ya estaban disponibles para R1.
Sirve como especificación ejecutable y baseline de ingreso; el núcleo de decisión
existente sigue en Rust. No se presume una ventaja futura de portar este verificador
a Rust sin implementarlo, contrastarlo y medirlo.

## Resultados de latencia

Cada fila agrupa **12.288 llamadas individuales** de tres repeticiones intercaladas.
Total: **49.152 ventanas**. Unidades de esta tabla: **milisegundos**.

| Camino | Mediana | p95 | p99 | p99.9 | Máximo |
|---|---:|---:|---:|---:|---:|
| Verificación, control sin reutilización | 3,101677 | 4,568540 | 5,850168 | 10,335944 | 23,036728 |
| Verificación, reutilización por paquete | 2,502995 | 3,785484 | 4,993081 | 7,284888 | 34,310908 |
| Ingreso + escenario R1, control | 3,127585 | 4,579887 | 6,123414 | 10,295934 | 52,971057 |
| Ingreso + escenario R1, reutilización | 2,474483 | 3,658305 | 4,596011 | 7,408657 | 16,368713 |

En verificación: mediana −19,302%, p99 −14,651%, p99.9 −29,519%, pero
**máximo +48,940%**. En ingreso con escenario: mediana −20,882%, p99 −24,944%,
p99.9 −28,043% y máximo −69,099%. No se descarta ningún pico ni se atribuye su causa
a la caché, GC o hipervisor sin evidencia causal. La mejora de mediana se conserva
en las tres repeticiones de ambos modos, pero no garantiza límites de latencia.

El mecanismo evita decodificaciones repetidas: de **471 referencias a nodos a 303
decodificaciones únicas** al recorrer una vez los 16 paquetes (−35,7%). El coste de
las rutas, encabezado, demás hashes y consistencia sigue incluido; no se anuncia ese
porcentaje como ahorro total de tiempo.

`ingress_scenario` incluye reset, prueba completa, ticket, chequeos de vigencia, IPC
local con un worker Rust ya iniciado, cálculo bajo precio supuesto y **denegación**
de autorización. No incluye el guardián financiero completo de R2, recepción de red,
consenso, oráculo/IRM ejecutados, simulación EVM de una liquidación, preparación/envío
al builder ni inclusión. No genera un candidato observado.

Las diferencias entre corridas explican que una mediana agregada del camino más largo
resulte ligeramente menor; **no se restan esos números para calcular coste de IPC**.
El control vacío de dos lecturas tuvo medianas de 200–211 ns por corrida; se registran
sus distribuciones completas sin sustraerlas. A esta escala no explica milisegundos,
pero sus máximos también muestran perturbaciones del entorno.

Los tiempos exactos en ns y todas las repeticiones están en [RESULTS.md](RESULTS.md).
El verificador recalcula los percentiles desde las muestras crudas y comprueba los
hashes de resultados observables, idénticos entre variantes y repeticiones de cada modo.

## Hardware e instrumento

- CPU reportada: AMD EPYC 9V74 80-Core Processor, x86-64; máquina virtual KVM con
  9 CPU lógicas visibles. Afinidad del benchmark y su worker heredada: CPU 0.
- Frecuencia física, carga del host, turbo e interrupciones no controlados; no se
  cambiaron políticas del sistema, aislamiento de núcleo o NUMA. `lscpu` y `/proc/cpuinfo`
  completos se conservan en `evidence/benchmark/benchmark.json`.
- Python 3.12.14 (Clang 22.1.3), GC activado. `trie 4.0.0`, `rlp 5.0.0`,
  `eth-hash 0.8.0`, `pycryptodome 3.24.1`; versiones y hashes de archivos registrados.
- Rust 1.90.0/LLVM 20.1.8; R1 sin cambios, O3, LTO fat, una unidad de generación,
  overflow checks activos y RUSTFLAGS vacío. solc 0.8.19 fijado por SHA-256.
- CLOCK_MONOTONIC_RAW, 64 llamadas de calentamiento por corrida; bytes y políticas
  disponibles antes de medir. Selección del caso, parsing y todo el trabajo indicado
  están dentro de la ventana. El resultado completo se consume fuera para obtener
  su checksum; esa serialización diagnóstica no se presenta como incluida.
- Corpus variado y observable; no hay eliminación del trabajo por el compilador.
  No hay sustracción de overhead, selección de la mejor repetición ni promedio de
  lote presentado como latencia individual. p99.9 sigue teniendo evidencia limitada
  de cola (aproximadamente 12 observaciones por distribución agrupada).

## Pruebas y procedencia

| Validación ejecutada | Resultado |
|---|---|
| Pruebas Python nuevas | 18/18, sin omisiones |
| Mutaciones de bytes de pruebas criptográficas | 256 casos, rechazados con y sin reutilización |
| Corpus de testigos sintéticos | 16; ambas raíces por caso coinciden con constructor MPT independiente |
| Slots Python frente a biblioteca Solidity upstream | 514 casos × 9 slots = 4.626 coincidencias |
| Regresión Rust R1 | 5/5, incluida traza integrada y 18 mutaciones del adaptador R1 |
| Regresión Rust del motor base | 8/8, guardianes, invalidación, prioridades y filtros preparados |
| Aislamiento de NQC | Verificador aprobado; 9/9 pruebas |
| Regeneración de fixtures | Bytes idénticos a los entregados |
| Percentiles, checksums y fuentes medidas | 12 corridas / 49.152 ventanas verificadas |
| Manifiestos anteriores | Base 76, R1 47, R2 49 archivos verificados, sin modificaciones |

Las pruebas incluyen rutas con hijos embebidos, extensiones, inclusión/ausencia,
metadatos falsos, JSON/RLP malformado, tamaños, slots repetidos o incompletos, identidad,
desajuste temporal, datos posteriores al bloque, tickets vencidos/sustituidos, reset de
ancla y restricciones de hilo. El contraste Solidity usa un harness puro en memoria;
no es la ejecución completa de Morpho. Los tests y el constructor independiente no
constituyen una prueba formal ni una auditoría externa.

El control de whitespace de Git señaló únicamente una línea vacía final en cada uno
de los dos logs de pruebas Rust. Se conservan las salidas originales, sin retocarlas;
el mismo control excluyendo evidencia no encuentra defectos en código o documentación.

El encabezado real recuperado corresponde al bloque **26210229**, hash
`0x586c2b51de3ca7138772636610f9f21c5e69ead65c1a12f9d911c1883ec6fbf6`.
Su SHA-256 documental es
`8970b6b207047daa838e3205c80c183b71c28cd4c9cd2fb5029caa4c3b0a9293`.
Se comprueba su hash de encabezado, pero **no hay un testigo completo Morpho asociado**
en los artefactos localizados. La prueba exige rechazo cuando falta ese testigo.

El inventario se limita a cuatro ramas técnicas y sus commits/búsquedas registrados
en [PROVENANCE.json](PROVENANCE.json). No se afirma una búsqueda exhaustiva de todos
los posibles archivos. Las fuentes upstream fijadas y el encabezado recuperado se
copian byte a byte con hashes; no se alteran para aprobar pruebas.

## Comparación con NQC019 y R2; objetivos recomendados

Esta revisión **no vuelve a etiquetar** los 119/250 ns históricos ni los 621 ns de R2:
eran controles/caminos locales con datos preparados, descritos y conservados en sus
respectivos informes. No incluían esta nueva verificación de pruebas. R3 añade trabajo
que antes faltaba; compararlo directamente como regresión del mismo componente sería
incorrecto. No se repitió la matriz completa R2 porque su código no cambió; sí se
verificaron todos sus hashes. Tampoco se repitieron los 30.006 casos diferenciales R1
ni sus 1.179 casos EVM anteriores; se conservaron y se ejecutó su suite Rust afectada.

Mantengo como **metas de investigación**, no compromisos:

- Filtro mínimo con hechos preparados: 20–50 ns; 5 ns continúa como exploración.
- Pipeline local preparado R2: 700 ns de mediana y 1.500 ns p99 como referencia de
  trabajo, conservando protecciones; p99.9 y máximos aún no ofrecen una garantía estable.
- Ingreso criptográfico R3: baseline medido alrededor de 2,5 ms con esta implementación
  y corpus. No se le exige artificialmente un presupuesto de nanosegundos.

No se suma ni se presenta ninguna combinación de estas cifras como latencia real del
bot completo. No se ha medido una ruta de red hasta builder ni inclusión Ethereum.

## Pendiente y recomendación

Se conserva la optimización como **experimental**, con ambas variantes disponibles.
La mejora de trabajo realizado y mediana está medida; la regresión del máximo impide
prometer un techo estable. Confianza alta en los resultados locales registrados y en
la equivalencia del corpus; preparación operativa insuficiente.

El siguiente paso técnico útil es obtener/importar un **testigo real reproducible**
y vincularlo a una política independiente de cadena, código y ejecución de oráculo/IRM.
Mientras falte, el sistema debe seguir diciendo desconocido y rechazar la autorización.
No se debe promover una predicción condicional a hecho observado ni suplir el preestado
intra-bloque usando el estado al final del bloque.

Después puede integrarse el verificador contrastado con el motor residente y eliminar
el IPC de laboratorio, midiendo la mejora. La autenticación se realiza por snapshot;
época, identidad, vigencia y autorización financiera permanecen en la decisión final.
No corresponde ampliar el número de servicios o agentes ni buscar 5 ns sacrificando
verificación. Este trabajo no interviene en rentabilidad histórica, financiación o
negociación comercial de NQC031/032.

Quedan sin implementar/verificar: consenso/finalidad, correspondencia verificable entre
runtime real y layout, ejecución autenticada de oráculo/IRM, replay de preestado real,
candidato observado, simulación completa, autorización financiera/no recurso y camino
hacia builder. No se gastó capital, no se firmó ni envió una transacción, no se desplegó
y no se activaron workflows o integraciones.
