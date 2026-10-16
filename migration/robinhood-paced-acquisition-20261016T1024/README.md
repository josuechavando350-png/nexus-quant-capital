# Adquisición persistente con límite global: preparación offline

16/oct/2026. Este incremento NO hizo consultas a Robinhood: **0 RPC reales,
0 segundos de captura, ninguna medición nueva de candidatos o rentabilidad**.
Se implementa un protocolo nuevo tras la parada HTTP 429 preservada en PR16.
No se sustituye ni reinterpreta aquella captura.

## Cambio técnico

`paced_acquisition.py` usa el transporte fijado en PR15 y el flujo de PR16,
en archivos nuevos. `pacing.py` impone al menos **350 ms entre inicios locales
de despacho RPC**, para índice, autenticación, cabeceras, lens y comprobaciones.
El reloj es monotónico; el último inicio real registrado, no la hora prevista,
determina la próxima admisión. No se acumula crédito durante una pausa.
La única rotación fría planificada conserva el mismo limitador, contador,
presupuesto de bytes y comienzo del plazo global.

Cada intento se conserva en `admissions.json`, incluso si el plazo vence antes
de poder enviar una petición. Las esperas consumen el límite único de **900 s**;
máximo **512 métodos RPC** para TODO el proceso. Se comprueban límite y estado
antes de esperar y después de despertar. Un despertar anticipado, exceso de
plazo, error HTTP/JSON/RPC o denegación cierra el lector. No hay reintento,
sesión de rescate, redirección, paralelismo ni proveedor alternativo.

La separación es una propiedad del despacho local: no garantiza cómo llegan
las peticiones al servidor, ni el alcance de cuotas compartidas. Los 350 ms
son una política conservadora, no un SLA ni una garantía de evitar otro 429.
El registro `started_ns` se toma inmediatamente antes de invocar el transporte
HTTP; incluye su preparación de conexión y no mide un paquete en la red.

## Reglas publicadas para la futura captura única

1. Fuente: registro parcial PR16, intervalo 88,646,281–89,912,197, 57 Borrow,
   30 cuentas. Archivo `../robinhood-acquisition-20261016T0922/evidence/pilot/registry.json`.
   Raíz `c57a798823c6163a54588353b92269fd98cd050cc96c9afb6123741d6752f7de`,
   fijada junto con el hash del archivo en `policy.json`.
2. Verificar cadena, límite inicial y checkpoint; seleccionar cabecera actual y
   anchor con 64 bloques de separación. Continuar SOLO desde **89,912,198**,
   por segmentos contiguos de hasta 10,000 bloques, máximo 40 segmentos.
   No repetir el tramo ya confirmado ni escanear historia anterior en este lote.
3. Conservar todas las fuentes/cuentas, incluidas cuentas con deuda cero. No
   seleccionar por salud ni liquidaciones conocidas. Congelar únicamente tras
   completar target, verificar límites canónicos y autenticar contratos.
4. Una rotación fría prevista después de la preparación sana; no rotar si falla.
   **12 rondas secuenciales**: cabecera latest, una lectura lens fijada por hash
   con `requireCanonical`, comparación de cabecera canónica. Reconciliar
   posiciones contra `totalBorrowShares` en cada hash. Retener cabeceras repetidas,
   todos los valores lentos y prefijos interrumpidos. Rechazar regresiones/reorgs.
5. Primaria: `admission_to_verified_ms`, desde ANTES de esperar admisión de
   cabecera hasta estado decodificado y canónico verificado. Secundarias:
   `request_to_verified_ms`, entradas, espera de cabecera y tiempo de cabecera.
   Reportar las once separaciones entre admisiones de rondas y cadencia observada.
   Separar primera conexión fría de las once elegibles para reutilización;
   comprobar metadatos de socket sin inferir conexión backend.
6. Tres solicitudes con 350 ms de separación imponen al menos **1.05 s de
   cadencia sostenida** en el despachador; una ronda aislada puede ser más corta.
   El objetivo supuesto de 1 s se evalúa INCLUYENDO la espera inicial, sin excluir
   rondas ni trasladar el inicio del cronómetro. No es ciclo de trading completo.
7. Cualquier denegación/error detiene la captura; conservar respuestas crudas,
   ledger, intentos de admisión, journal encadenado y archivos parciales. No
   reemplazar el resultado con otra captura. Auditar offline con `audit_paced.py`.

Hash raíz de fuente (64 caracteres):
`c57a798823c6163a54588353b92269fd98cd050cc96c9afb6123741d6752f7de`.
SHA256 del archivo:
`67d8a5c619bf025e410e785838e9f08b5919a6e844112eb22911b17369c501ee`.

Endpoint único heredado: `https://docs-demo.robinhood-mainnet.quiknode.pro/`.
Mismas dependencias exactas PR15, TLS verificado, proxy/no_proxy/CA respetados,
20 s máximo por llamada y plazo restante, 2 MiB por cuerpo y 32 MiB acumulados.
No se habilitan workflows, firmas, transacciones, trading, gastos o despliegues.

## Evidencia y validación

`evidence/verification/` contiene recibos de **114 pruebas Python**: 22 sobre el
nuevo lector/auditor (12 comportamientos portados de PR16 y 10 específicos del
limitador), más 92 regresiones/aislamiento. El flujo sintético inyecta fallos
en las **59 fronteras RPC**. Prueba continuidad del límite al rotar, cuota de
peticiones, espera/plazo, bytes, reorgs, JSON/RPC/HTTP, paradas y manipulación.

`evidence/synthetic/` conserva cuatro trazas totalmente artificiales, incluyendo
paradas antes de completar índice y después de la rotación. **No son estado ni
latencia de Robinhood.** En el caso ideal con transporte instantáneo, las doce
rondas marcan 700 ms desde despacho, pero **1,050 ms incluyendo admisión** y
las once separaciones son 1,050 ms. El objetivo de 1 s queda correctamente
rechazado; no se contabiliza una espera externa como una mejora.

`evidence/offline-summary.json` recoge hashes, resultados y preservación de
manifiestos PR13–PR16. El replay original de PR16 sigue detenido con 10 RPC y
cero observaciones. Originales: 377 blobs; 106 workflows deshabilitados, cero
activos. Rust/Solidity sin cambios ni nueva ejecución. No se afirma que pase
todo el histórico de descubrimiento global de tests del repositorio.

## Reproducción y siguiente paso

```bash
PYTHONPATH=/workspace/scratch/f9e56e91df85/nqc-http-deps python migration/robinhood-paced-acquisition-20261016T1024/verify_offline.py
```

`prepare.py policy` y `prepare.py lock` son pasos de preparación **previos a
publicar**; no ejecutarlos para modificar un protocolo ya registrado. El comando
de captura y el commit publicado están en `CONTINUITY.md`. Aún no se ejecutó.
Antes de medir, verificar lock y ausencia de una ejecución/evidencia posterior.

APIs nuevas contrastadas el 16/oct/2026 en documentación primaria de Python 3.12:
[monotonic_ns](https://docs.python.org/3.12/library/time.html#time.monotonic_ns) y
[sleep](https://docs.python.org/3.12/library/time.html#time.sleep). El reloj monotónico
no sigue ajustes de hora; sleep puede exceder lo solicitado. Por eso se vuelve
a comprobar el plazo al despertar. Las APIs de red son las mismas de PR15.

Confianza técnica alta en los invariantes probados offline, limitada hasta una
captura real. **Captura rentable, coste AA/Nitro/DA, admisión de bundler y
patrocinio prepagado financiable siguen sin demostrar.** No hay nuevos datos
de cobertura o candidatos; ausencia de medición no equivale a cero candidatos.
