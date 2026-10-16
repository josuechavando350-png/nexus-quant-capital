# Registro persistente de prestatarios y lecturas agrupadas

Este cambio sigue al piloto de PR11, cuya ventana de 2,048 bloques no encontró
prestatarios. Añade un registro reanudable de eventos Borrow del mercado
wsNET/USDG de Morpho en Robinhood y mide la lectura de posiciones fijadas por
hash. La deuda encontrada y las señales de riesgo no se presentan como ingresos.

El protocolo se publicó antes de la primera consulta en
[`06f492b9c8e5f5c53e0079f9b18d6590a967b5f1`](https://github.com/josuechavando350-png/nexus-quant-capital/commit/06f492b9c8e5f5c53e0079f9b18d6590a967b5f1),
rama `nqc/registry-protocol-20261016`. `registration-sources.json` fija los ocho
archivos de implementación, pruebas, reglas y política. La base es PR11 en
`89f1e9a6bda3c8f35bd2153856aea7c98813eea9`; sus primitivas y matemática se reutilizan
sin cambios. El código y la selección registrados no se ajustan al resultado.

## Resultado de la medición

El primer piloto terminó el **16 de octubre de 2026, 05:55:38–06:03:22 UTC**
(15 de octubre 23:55:38–16 de octubre 00:03:22 en Ciudad de México), en
**463.77 segundos**. La auditoría offline reconstruyó los datos desde las
respuestas originales. Hubo 203 métodos RPC en 158 peticiones HTTP, sin errores.

| Medida del primer piloto | Resultado |
| --- | ---: |
| Intervalo indexado, inclusive | 89,446,281–89,846,280 |
| Bloques / tramos contiguos | 400,000 / 40 |
| Duración del intervalo según timestamps de cadena | 40,496 s |
| Eventos Borrow / cuentas distintas congeladas | 15 / 10 |
| Cuentas con deuda positiva, en cada bloque observado | 9 |
| Participaciones de deuda cubiertas | 10.1447045744% |
| Participaciones de deuda sin cubrir | 89.8552954256% |
| Bloques distintos observados después de congelar cuentas | 3 |
| Cuentas dentro del umbral de riesgo de 1%, por bloque | 0 |
| Cuentas con deuda sobre su máximo saludable, por bloque | 0 |
| Rutas simuladas / beneficio realizado medido | 0 / sin medir |

Las cuentas cubrieron 87,282,627,353,498,696 participaciones de un total de
860,376,235,833,277,471. El mercado almacenaba **922,821.533074 USDG** de deuda;
la suma de deuda devengada de las cuentas observadas fue de 93,617.992796 a
93,618.413537 USDG. Estas son obligaciones de los prestatarios. No representan
un excedente capturable. Una cuenta sin deuda permaneció en el registro.

El menor margen de salud calculado pasó de 711 a 708 puntos básicos por encima
de la deuda actual; la regla de señal exige como máximo 100. Es una comparación
de deuda y máximo saludable, no una previsión del precio ni una garantía de
salud futura. La ausencia de señales solo corresponde a estas cuentas y bloques.
La salud del 89.86% de deuda no cubierta continúa sin observarse.

| Bloque | Entradas batch, s | Entradas desde cabecera, s | Bloques posteriores al índice |
| --- | ---: | ---: | ---: |
| 89,849,772 | 12.688 | 12.689 | 3,492 |
| 89,850,409 | 13.982 | 13.984 | 4,129 |
| 89,850,614 | 15.642 | 15.644 | 4,334 |

En el primer bloque, la repetición secuencial tomó **42.121 segundos**, frente a
12.688 en batch, con igualdad exacta de estado y cálculos. La mejora de esa pareja
no acredita cumplimiento del presupuesto hipotético de un segundo ni ejecución
al siguiente bloque. Los huecos posteriores al índice quedan visibles; el
registro no se atribuye cobertura sobre esos bloques mientras se leen posiciones.

La continuación real, usando exactamente el mismo protocolo registrado y el
checkpoint anterior, terminó entre **06:04:06 y 06:06:35 UTC**, en 149.93 segundos.
Añadió únicamente **4,946 bloques**, 89,846,281–89,851,226, sin nuevos Borrow.
Conservó las diez cuentas y los 15 eventos. El registro acumulado abarca
**404,946 bloques en 41 tramos**; no se repitieron las 400,000 alturas iniciales.
El registro inicial quedó intacto y el nuevo registra su hash como antecedente.

Esta continuación completó otros tres bloques de posiciones, con la misma
cobertura de deuda, nueve cuentas endeudadas y cero señales dentro del umbral.
Las entradas batch tardaron **17.549, 12.056 y 20.222 segundos**. Su primera
comparación secuencial tardó **46.501 segundos**, de nuevo con igualdad exacta.
Los bloques consultados fueron 89,851,548, 89,852,278 y 89,852,466, dejando 322,
1,052 y 1,240 bloques posteriores al nuevo checkpoint sin indexar en cada ronda.

En total: **274 métodos RPC, 199 peticiones HTTP, seis bloques distintos de
posiciones, dos comparaciones pareadas y cero errores de proveedor**. Las seis
rondas no son muestras independientes del mercado: observan las mismas cuentas.
En todas se superó el presupuesto de un segundo. La continuación valida
persistencia y lectura incremental; no convierte el registro en completo ni en
un servicio continuo. Ambas ejecuciones terminaron.

El avance es una cohorte persistente no vacía, cobertura cuantificada y lectura
agrupada comprobada contra lectura secuencial. **La cobertura sigue siendo
insuficiente y la captura rentable continúa sin demostrarse.** Hace falta
incorporar historia anterior con procedencia verificable y cerrar los huecos al
avanzar, además de medir acceso de baja latencia. Solo con esa cobertura y estados
actuales podrá evaluarse supervivencia y coste de rutas candidatas.

## Qué queda implementado

- `registry.py`: prefijo contiguo, eventos deduplicados, enlaces SHA-256 entre
  tramos, escritura atómica y conservación de cuentas anteriores. No elimina
  cuentas por haber repagado: las reconcilia de nuevo al observar posiciones.
- `collect.py`: valida bloques de eventos y ancla, congela todos los prestatarios
  antes de observar salud y autentica los tres contratos y parámetros del mercado.
  Un registro parcial no se promociona a cohorte del objetivo completo.
- `rpc_batch.py`: hasta cuatro elementos por POST, asociación de respuestas por
  ID y límites de solicitudes, tiempo y bytes. Una respuesta incompleta o un
  error de cualquier elemento detiene el lector sin reintentos.
- `audit_capture.py`: reconstruye tramos y posiciones desde las respuestas
  originales, verifica diario y hashes, compara lecturas del mismo bloque y
  recalcula cobertura de deuda, señales y latencia.

La continuación recibe una copia del registro anterior, verifica su checkpoint
canónico y avanza desde el bloque siguiente, sin saltar huecos. Un cambio de hash
invalida esa copia y exige reconstrucción; no hay rollback automático. Se
conservan la versión anterior y el prefijo validado si se interrumpe una nueva
ejecución. La continuación está probada con fixtures sintéticas y con la ejecución
remota descrita arriba; ambas clases de evidencia se conservan por separado.

La cobertura se expresa como `sum(position.borrowShares) / market.totalBorrowShares`.
Se conservan numerador y denominador exactos y un porcentaje truncado a puntos
básicos. No se divide entre cero. La igualdad solo acredita todas las
participaciones de deuda positiva en el bloque consultado, bajo la evidencia de
esa fuente; no acredita todo el historial, cuentas sin deuda, otros mercados ni
aperturas posteriores. El historial anterior al inicio y los bloques posteriores
al checkpoint siguen fuera del índice.

## Límites de la evidencia

Se usa un endpoint público de demostración como única fuente, sin prueba
criptográfica de estado/logs ni consenso entre proveedores. Los hashes permiten
detectar alteraciones frente al paquete publicado; no certifican por sí solos
la hora de captura ni la veracidad del proveedor. Un buffer de 64 bloques no es
una garantía de finalidad.

La comparación batch/secuencial usa el mismo bloque y las mismas vistas, primero
batch y después secuencial. Hay una pareja por ejecución, dos en total; no aísla
caché, carga del nodo, red o transporte. Cada elemento batch sigue contando como
solicitud RPC. El
tiempo de entradas excluye la comprobación canónica posterior; la métrica desde
cabecera incluye el trabajo local hasta tener las entradas. Ninguna mide envío,
admisión, inclusión, captura o costes de ejecución.

Este ensayo no ejecuta rutas. Las señales de deuda y salud necesitan simulación
posterior y medición de supervivencia; su presencia no acredita rentabilidad.
Bundler, patrocinio, coste del ciclo AA/Nitro/DA y financiación comercial siguen
requiriendo evidencia prospectiva. No se usan claves, fondos, suscripciones ni
transacciones, y no queda un servicio en segundo plano.

## Verificación y reproducción

**25 pruebas nuevas + 22 de regresión de PR11 + nueve de aislamiento: 56 Python
aprobadas.** Las pruebas de continuación, reorganización, límites, respuestas
fuera de orden, fallos parciales y cobertura usan datos sintéticos identificados.
Los verificadores conservan 377 blobs originales, 106 workflows deshabilitados
y cero activos. No se modificó Solidity/Rust ni se ejecutaron sus suites.

Desde la raíz del repositorio, sin red:

```bash
python -m unittest discover -s migration/robinhood-borrower-registry-20261016 -p 'test_*.py' -v
python migration/robinhood-borrower-registry-20261016/audit_capture.py \
  migration/robinhood-borrower-registry-20261016/evidence/pilot \
  --out /tmp/nqc-registry-audit.json
python migration/robinhood-borrower-registry-20261016/audit_capture.py \
  migration/robinhood-borrower-registry-20261016/evidence/resume \
  --out /tmp/nqc-registry-resume-audit.json
python migration/robinhood-borrower-registry-20261016/summarize.py \
  migration/robinhood-borrower-registry-20261016/evidence/pilot \
  --out /tmp/nqc-registry-summary.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

Una nueva ejecución de `collect.py --out DIRECTORIO_NUEVO --registration-commit
COMMIT` consulta otro periodo real y requiere volver a publicar las reglas si se
cambian. `--resume-registry RUTA/registry.json` conserva cuentas del prefijo previo;
el destino es siempre nuevo. El argumento del commit identifica el registro:
hay que contrastar el commit publicado y los hashes, no confiar solo en el texto
del argumento. Los límites están en `PRE_REGISTER.md` y `policy.json`.

`summarize.py` se añadió después del registro del protocolo para presentar el
diagnóstico. No participa en selección, captura ni decisiones, y sus resultados
proceden de `audit_capture.py`. Los archivos `pilot-report.json` y
`resume-report.json` conservan las posiciones y cálculos; sus resúmenes son los
archivos `pilot-summary.json` y `resume-summary.json`. `MANIFEST.sha256` fija el
paquete completo.

Las fuentes primarias de interfaces y límites están enlazadas en
`PRE_REGISTER.md`. No se reutiliza la certificación original de PFT/Census para
afirmar certificación de este productor nuevo.
