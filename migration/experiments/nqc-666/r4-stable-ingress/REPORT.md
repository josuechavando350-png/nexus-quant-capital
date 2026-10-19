# NQC666 R4 — integración local y correcciones de estabilidad

**Implementado:** verificación R3 conectada a las fórmulas Rust R1 en el mismo
proceso; importador offline; tickets ligados a instancia/época/posición; expiración
monotónica y descarte de resultados tardíos. Los problemas reproducidos de tickets
entre instancias y espera de pipe quedan corregidos en el camino R4.

**No está todo estabilizado:** las colas del ingreso completo regresaron en la primera
matriz, y todavía falta el testigo real completo. El único intento de lectura pública
de encabezado devolvió HTTP 403; se detuvo y se conservó el error. No se obtuvo una
respuesta de estado ni se fabrica un testigo para reemplazarla.

Fecha de trabajo: 18 de octubre de 2026 en Ciudad de México. Base inmutable:
`b68361d28f2ee971f941c0eb5440135c9df97b83`. Rama experimental:
`research/nqc-666-third-eye-20261018`. Solo se añade `r4-stable-ingress`.

## Correcciones verificadas

| Problema concreto | Cambio | Comprobación |
|---|---|---|
| Ticket de otra instancia aceptado en R3 | Identidad del ticket y sesión, época, bloque, mercado y prestatario | Reproducción R3; copia y ticket ajeno rechazados en R4 |
| Worker silencioso bloquea `readline` de R3 | Cálculo Rust en biblioteca local por valor, sin pipe en R4 | Reproducción acotada >250 ms en R3; camino R4 sin proceso hijo |
| Repetir hora del llamador mantiene vigente el ticket | Fecha límite monotónica independiente tras recibir el snapshot | Reloj del llamador congelado y avance monotónico: rechazo |
| Resultado disponible después de caducar o del presupuesto | Revalidación al terminar e invalidación del estado | Inyección de demora en verificación y cálculo; salida descartada |
| Cancelación, excepción, reentrada o resultado inconsistente | Revocación antes de permitir reutilización | Pruebas de `BaseException`, reentrada y resultados inválidos |

Presupuestos iniciales: 50 ms para verificación, 5 ms para escenario preparado.
Son **plazos de aceptación**, no una promesa de tiempo máximo de ejecución. No
interrumpen una pausa del sistema operativo. Un resultado tardío se descarta con su
latencia registrada; no se elimina del benchmark.

La biblioteca utiliza la implementación R1 sin cambiar sus fuentes o fórmulas. El
wrapper tiene estructuras de tamaño fijo por valor y no recibe punteros, mantiene
estado global ni ejecuta I/O. El binding comprueba hash y versión de ABI antes de usarla.
Esto presupone binario y sistema de archivos locales de confianza. Compartir proceso
también significa que un fallo fatal nativo puede terminar Python; no se presenta como
aislamiento de fallos de proceso. [DESIGN.md](DESIGN.md) detalla esa frontera.

## Matriz principal: 208.896 llamadas

24 corridas intercaladas, tres repeticiones, sin recortar picos, con resultados
equivalentes en cada intento aceptado. **Cero descartes** en esta matriz; los fallos
por tiempo se comprueban mediante inyección determinista en los tests.

Matemática preparada y escenario sobre snapshot ya verificado, en **microsegundos**:

| Camino | Mediana | p95 | p99 | p99.9 | Máximo |
|---|---:|---:|---:|---:|---:|
| Matemática R1 por IPC | 10,215 | 16,675 | 34,491 | 298,054 | 3.195,316 |
| Matemática R1 por ABI nativo | 7,551 | 12,088 | 27,181 | 91,236 | 1.123,603 |
| Escenario R3 + IPC | 13,861 | 16,785 | 63,584 | 192,777 | 2.117,161 |
| Escenario R3 + nativo | 11,036 | 17,266 | 58,848 | 216,112 | 1.702,194 |
| Escenario R4 + nativo | 12,799 | 14,512 | 37,957 | 188,991 | 812,109 |

La matemática integrada reduce mediana **26,08%**, p99 **21,19%** y p99.9 **69,39%**
frente al IPC. El escenario R4, incluyendo sus controles nuevos, reduce mediana
**7,66%**, p99 **40,30%** y máximo **61,64%** frente a R3+IPC. Frente a R3+nativo,
los controles R4 añaden coste: la mediana pasa de 11,036 a 12,799 µs (+15,98%).
Se conserva ese coste porque corrige problemas de integridad reproducidos.

Ingreso completo con pruebas y escenario, en **milisegundos**:

| Camino | Mediana | p95 | p99 | p99.9 | Máximo |
|---|---:|---:|---:|---:|---:|
| R3 + IPC | 2,513732 | 3,793105 | 4,762068 | 7,002463 | 16,438908 |
| R3 + nativo | 2,478028 | 3,606628 | 4,400950 | 6,000962 | 9,799836 |
| R4 + nativo | 2,610917 | 4,066142 | 5,988854 | 11,649239 | 14,473562 |

Frente a R3+IPC: mediana **+3,87%**, p99 **+25,76%**, p99.9 **+66,36%**, máximo
−11,96%. No se declara R4 más rápido en todo el sistema. Se conserva la matriz y se
realiza un contraste emparejado adicional para investigar esta regresión específica;
su hipótesis previa y resultados están en `PAIRED_ADDENDUM.md` y `PAIRED_RESULTS.md`.
No se cambia el código de ejecución entre ambas mediciones ni se sustituye la primera
por la que resulte más favorable.

El contraste adicional de 12.288 pares / 24.576 ventanas compara R3+nativo con
R4+nativo: mediana +0,80%, p99 −4,19%, p99.9 −5,68%, pero máximo +25,30%
(19,126 → 23,964 ms). La mediana de diferencia dentro de cada par fue +9.464 ns.
No hubo descartes ni discrepancias. El resultado confirma variabilidad temporal
pendiente de resolver; no prueba estabilidad del sistema completo. Total de ventanas
conservadas entre ambos experimentos: **233.472**.

El escenario preparado excluye verificación criptográfica del snapshot. El ingreso
incluye JSON, pruebas, reset, ticket, cálculo condicional y denegación de autorización.
Ninguno mide consenso, ejecución de oráculo/IRM, simulación de liquidación, el guardián
financiero completo de R2, red, builder o inclusión. El worker y la biblioteca están
iniciados/cargados antes de medir. Los buffers/políticas ya existen. La serialización
diagnóstica del resultado y checksum se hace fuera de la ventana y así se declara.

Estas cifras tampoco sustituyen los nanosegundos del núcleo preparado Rust de versiones
anteriores: incluyen integración Python/ABI y controles distintos. No se suma una
colección de microbenchmarks para inventar latencia extremo a extremo.

## Pruebas ejecutadas y procedencia

- 16 tests Python nuevos y 2 tests Rust nuevos: todos aprobados.
- 14.194 casos de paridad de ABI: 6.002 casos de salud del corpus R1 guardado y 8.192
  adicionales contrastados con el ejecutable R1 original. Resultados y errores exactos.
- 4.096 llamadas en cuatro hilos de prueba para comprobar independencia de requests
  por valor; no se añade ejecución paralela al gateway.
- Regresiones: 18 tests Python R3, 5 tests Rust R1, 8 tests Rust del motor base y
  9 tests de aislamiento aprobados. Verificador de aislamiento, formato y Clippy aprobados.
- Demostración del importador con fixture sintético: conserva archivos/hashes y produce
  hechos relativos a la raíz y escenario condicional, siempre con autorización falsa.
- Prueba negativa con encabezado histórico real y testigo ausente: rechazo sin publicar
  hechos parciales. No se le llama “testigo real incorporado”.
- Manifiestos base/R1/R2/R3: 76/47/49/59 archivos verificados respectivamente, inmutables.

No se repitieron las matrices completas antiguas, los 1.179 casos EVM R1 ni los 514
casos Solidity de slots R3, porque sus fuentes no cambiaron. Se conserva esa evidencia
y se ejecutaron las regresiones correspondientes. Los ensayos actuales no son auditoría
formal ni garantía para cualquier host, entrada o arquitectura.

Los logs crudos Rust pueden terminar con una línea vacía adicional; se conservan sin
retocarlos. El chequeo de whitespace se aplica a código y documentación por separado.

## Entorno y reproducibilidad

CPU virtual AMD EPYC 9V74, x86-64, KVM, nueve CPU visibles; afinidad a CPU 0. Frecuencia,
interrupciones y carga del host no controladas. GC Python activo. No se alteró la
configuración del sistema. Reloj de medida CLOCK_MONOTONIC_RAW con controles por muestra;
las muestras no se corrigen restando overhead. Los metadatos conservan `/proc/cpuinfo`,
`lscpu`, hashes de fuentes, binarios y versiones.

Python 3.12.14; Rust 1.90.0/LLVM 20.1.8, O3, LTO fat, una unidad de generación,
overflow checks activos, `panic=abort` para la biblioteca y RUSTFLAGS vacío. Se reutiliza
el entorno Python R3 sin instalar dependencias. El benchmark principal corrió de
00:42:36 a 00:44:18 UTC del 19 de octubre (tarde del 18 en México).

Biblioteca medida SHA-256:
`1cc575699de5a9395dc95b6cc17fbabae0c355459948ba91ef11d204ef0388f4`.
El binario se reproduce compilando; otra ruta/toolchain puede cambiar su hash. Se
entregan fuentes, lockfile, desensamblado, corpus, resultados y muestras crudas.

## Estado de incorporación y continuación

**Incorporado:** puente local a Rust, gateway reforzado e importador de evidencia
con trazabilidad. **Pendiente:** el paquete real de cuenta/código/slots y su procedencia,
validación independiente de cadena, asociación runtime/layout y oráculo/IRM ejecutados
sobre estado coherente. Un encabezado aislado o un precio supuesto no cubren esos pasos.

La consulta a `https://ethereum-rpc.publicnode.com`, endpoint público documentado,
solicitó únicamente `eth_getBlockByNumber("finalized", false)` y devolvió HTTP 403.
No se solicitaron firmas, transacciones, permisos, credenciales ni servicios de pago.
No se rodeó la restricción. Para completar la incorporación real hace falta un paquete
obtenido por una fuente autorizada y verificable; la CLI ya permite importarlo offline.

Conservar R4 como integración experimental por las correcciones probadas. No sustituir
todavía un camino operativo ni afirmar “todo estabilizado”: quedan colas del host,
ingreso completo, evidencia real y autorizaciones externas sin resolver. La siguiente
optimización debe atacar el coste observado de pruebas de estado con el mismo corpus,
no retirar vigencia, identidad o guardianes para alcanzar un número de nanosegundos.

Confianza alta en las correcciones y paridad del corpus local; confianza limitada en
límites temporales operativos y ninguna certificación comercial. Main y fuentes anteriores
permanecen intactos; no se interviene en los trabajos financieros NQC031/032.
