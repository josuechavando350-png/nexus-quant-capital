# Adquisición completa real: 12 rondas, sin errores, margen aún no demostrado

Captura única del **16/oct/2026, 11:19:21.046–11:19:58.633 UTC**
(05:19:21–05:19:58, Ciudad de México). **89 métodos RPC / 89 HTTP**, 37.587 s
de journal, 37.595 s reportados por el proceso, salida 0, cero errores.
53 consultas de preparación y 36 de observación. Se cerró la captura; no se
hizo ninguna consulta adicional ni se relanzó para sustituir resultados.

Protocolo publicado previamente en **`f82249cd9844d686b13e637b5d22a7eca88985d1`**,
PR17. Sus 57 fuentes, política, README, trazas sintéticas y manifiesto siguen
intactos. Este informe es nuevo; no convierte el rechazo histórico PR16 en éxito.

## Resultado de adquisición

Cabecera + lectura única lens fijada por hash + verificación canónica en sesión
persistente. La medida principal comienza **antes de esperar admisión** de la
cabecera y termina después de decodificar/comprobar el estado. No incluye ruta,
envío, inclusión, gas, financiación o beneficios.

| Medida | Primera ronda fría | Once rondas reutilizadas: mín. / mediana / máx. |
|---|---:|---:|
| Admisión a estado verificado, principal | 4,270.030 ms | 980.560 / 1,051.273 / 1,130.925 ms |
| Despacho HTTP local a estado verificado | 4,019.207 ms | 741.051 / 807.890 / 825.449 ms |
| Espera previa a la cabecera | 250.823 ms | 224.191 / 243.165 / 310.409 ms |
| Admisión a entradas recibidas | 3,944.308 ms | 642.349 / 675.229 / 732.449 ms |
| Solo lectura lens, sin esperas anteriores | 129.176 ms | 49.899 / 74.977 / 111.509 ms |

**Solo 2/12 rondas cumplieron el objetivo supuesto de 1 s** (2/11 reutilizadas).
No se ha probado adquisición sostenida subsegundo. La comparación PR15 excluía
la petición inicial de cabecera, por lo que no es un control pareado de este
experimento. Todas las doce rondas y respuestas están conservadas.

Doce bloques distintos, 90,037,442–90,037,555; ninguna cabecera repetida. En las
36 peticiones de medición se observó un socket cliente nuevo y 35 reutilizaciones,
por el proxy configurado. Esto no prueba reutilización de conexión backend.
El arranque inicial de preparación tardó 3,763.366 ms y no se descarta.

## Frecuencia y esperas: qué se sostuvo realmente

Los **88 intervalos entre inicios RPC** fueron >=350.156 ms: cero infracciones
del mínimo de 350 ms, incluida la rotación fría planificada. Las esperas de
admisión sumaron **21.978 s**, incluidos en el plazo total. No hubo 429 en esta
muestra; no es garantía de capacidad futura, cuota exclusiva o SLA.

Las diez separaciones entre despachos de cabeceras reutilizadas fueron
1,050.875–1,052.488 ms. Las separaciones entre *solicitudes de admisión* fueron
981.588–1,132.486 ms, media **1,053.391 ms**, unas **0.949 adquisiciones/s**.
Ambas series se conservan: una respuesta final más rápida puede adelantar la
siguiente solicitud de admisión, sin adelantar su despacho permitido. Por ello,
un intervalo aislado de admisión inferior a 1.05 s NO viola el limitador ni
demuestra cadencia subsegundo sostenida.

Incluyendo el intervalo frío, la tasa sobre las once separaciones entre
admisiones fue 0.743 adquisiciones/s. La ventana de las doce observaciones,
desde primera admisión hasta última verificación, duró 15.837 s. Son métricas
descriptivas de una muestra corta, no percentiles de servicio ni prueba de
supervivencia de oportunidades. La edad respecto al timestamp entero del
bloque al recibir la comprobación final fue 1.058–1.624 s; su resolución de
un segundo impide inferir de ahí edad exacta o momento de disponibilidad.

## Registro y oportunidades observadas

Se revalidó el prefijo PR16 y se continuó exclusivamente la cola
**89,912,198–90,037,169**: 124,972 bloques, cuatro Borrow y una cuenta nueva.
Trece segmentos nuevos; ninguna repetición de los 10,000 bloques ya confirmados.
Se autenticó el target y se congeló la cohorte antes de medir posiciones.

- Registro contiguo: **88,646,281–90,037,169**, 1,390,889 bloques, 61 Borrow.
- Cohorte: **31 cuentas**, 25 con deuda en los doce hashes observados; se
  conservaron las seis cuentas sin deuda.
- Cobertura de `borrowShares`: **20.6983288874%**; falta **79.3016711126%**.
- En esos mismos hashes, la cohorte anterior cubre 20.6808342479%; la cuenta
  nueva aporta **0.0174946396 puntos porcentuales**. No atribuirle toda la
  diferencia frente a mediciones anteriores en otros bloques.
- **Cero candidatos y cero cuentas calculadas como liquidables** en esta
  muestra y cohorte. No prueba que no existan oportunidades fuera de ellas.
- Cola posterior al anchor sin indexar durante las rondas: **273–386 bloques**.
  Cohorte congelada, no universo histórico ni cobertura continua completa.

No hubo operaciones reales, firmas, envíos, rutas simuladas o compromisos de
fondos. **Rentabilidad neta, admisión de bundler, patrocinio prepagado financiable
y costes completos AA/Nitro/DA siguen sin demostrarse.** Las deudas observadas
no son ingresos.

## Evidencia y reproducción offline

Respuestas originales, `requests.json`, `admissions.json`, journal encadenado,
registro y cohorte: `../robinhood-paced-acquisition-20261016T1024/evidence/pilot/`.
`evidence/audit.json` reproduce exactamente el flujo y los archivos persistidos;
`evidence/summary.json` conserva cada ronda, métricas y cálculos de cobertura.
`evidence/execution.json` recoge comando, salida final y código de proceso.

Fuente nueva para continuidad:

```text
migration/robinhood-paced-acquisition-20261016T1024/evidence/pilot/registry.json
raíz: 8740288f2899e8fc2056d56291ad5369f8c37d46a1e8139a5b41f3501601aaf0
SHA archivo: 0346642a39cc0227bee8aa6e16f6a592d45fdb5e8ffbb29bb01a4c82aa5774d6
```

**37 pruebas aprobadas en esta ejecución**: 22 de adquisición con limitador
y 9 de aislamiento antes de capturar; 6 comprobaciones independientes del informe
después. Un test nuevo leyó inicialmente claves incorrectas de segmento y falló;
se corrigió el test, sin cambiar capturas ni código registrado. Se conserva ese
fallo en `evidence/verification/report-test-correction.json` y el recibo final.
Las 114 pruebas de PR17 son históricas: no se afirma haber repetido todas aquí.

Manifiestos PR13–PR17 intactos: 210/175/77/38/147 archivos respectivamente;
57 fuentes registradas intactas; 377 blobs originales verificados, 106 workflows
deshabilitados y cero activos. Rust/Solidity sin cambios ni nueva ejecución.
El fallo incidental de `ps` ("fatal library error, lookup self") se resolvió
para la inspección leyendo `/proc`: 15 entradas, ninguna captura concurrente;
también se comprobaron seis worktrees sin evidencia de ejecución previa.

```bash
PYTHONPATH=/workspace/scratch/f9e56e91df85/nqc-http-deps python migration/robinhood-paced-acquisition-20261016T1024/audit_paced.py migration/robinhood-paced-acquisition-20261016T1024/evidence/pilot --out /tmp/nqc-paced-audit-check.json
python -m unittest discover -s migration/robinhood-paced-capture-20261016T1117 -p 'test_*.py' -v
```

El comando de captura ya se ejecutó: **no volver a lanzarlo**. `verify_preflight.py`
también es un recibo del estado previo; ahora debe rechazar que el directorio
de captura exista. Los programas de informe no realizan llamadas RPC.

## Valor y próximo incremento

Avance técnico bueno: primera medición completa con esperas, cola actualizada,
presupuesto y ritmo respetados, sin errores en esta muestra. Confianza alta en
reproducibilidad de esta evidencia; limitada para generalizar latencia o cuota.
La ausencia de candidatos y el 79.30% no cubierto limitan la conclusión comercial.

El siguiente incremento recomendado es **ampliar cobertura histórica** con un
protocolo NUEVO para 88,246,281–88,646,280 (400,000 bloques), tomando la nueva
raíz como fuente, conservando cuentas y sin seleccionar por salud. Compartir
el mismo limitador/budget global entre historia, unión, cola y observaciones;
probar offline y publicar antes de medir. Si después aparecen candidatos,
medir supervivencia y costes de ejecución completos. No repetir este benchmark
para sustituir una muestra que no alcanzó el objetivo de un segundo.
