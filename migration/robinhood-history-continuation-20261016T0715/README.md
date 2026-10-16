# Segundo tramo anterior y auditoría de interrupciones

**La cobertura medida alcanza 20.2407525% de borrowShares: 30 cuentas, 24 con
deuda positiva.** Se corrigió el auditor de capturas parciales y se añadió una
medida del tiempo hasta disponer de estado verificado. No hubo señales en los
tres bloques observados; sigue sin medirse captura rentable.

Base inmutable: PR13 en `66f0abbf6d44c6e98a0070b2109ee375ae42de3b`.
El protocolo se publicó antes de consultar Robinhood en
[`5bfbad3898d1f2b97554c2485340ef5a007d8e95`](https://github.com/josuechavando350-png/nexus-quant-capital/commit/5bfbad3898d1f2b97554c2485340ef5a007d8e95).
Los 26 archivos del manifiesto de fuentes siguen idénticos. Los lectores,
bytecode y matemática heredados se reutilizan sin modificar PR13 ni sus archivos.

## Resultado real

Captura del **16 de octubre de 2026, 07:24:24–07:32:04 UTC**, 460.83 segundos.
**171 métodos RPC, 149 peticiones HTTP y cero errores del proveedor.** El auditor
reconstruyó las ventanas, la unión, las posiciones y los tiempos a partir de
respuestas originales y journal encadenado.

| Medida | Resultado |
| --- | ---: |
| Nuevo intervalo anterior | 88,646,281–89,046,280 |
| Bloques anteriores / Borrow / cuentas nuevas | 400,000 / 18 / 7 |
| Actualización reciente / Borrow / cuentas nuevas | 24,716 bloques / 1 / 0 |
| Intervalo acumulado | 88,646,281–89,902,197 |
| Bloques / tramos / Borrow acumulados | 1,255,917 / 127 / 57 |
| Cuentas / cuentas con deuda positiva | 30 / 24 |
| Cobertura de deuda, en los tres bloques | 20.2407525118% |
| Deuda fuera de la cohorte, en esos bloques | 79.7592474882% |
| Cohorte anterior, recalculada en esos mismos bloques | 17.2429406706% |
| Aporte de las siete cuentas nuevas | 2.9978118413 puntos porcentuales |
| Señales bajo el umbral de 100 bps / posiciones no saludables | 0 / 0 por bloque |

El numerador es **175,106,048,058,791,785 borrowShares** y el denominador,
**865,116,294,250,755,886**. Faltan 690,010,246,191,964,101 participaciones.
La cohorte de PR13 cubría 16.804189% en su captura anterior, pero ahora sus
mismas cuentas cubren 17.242941%. Por tanto, no se atribuye toda la diferencia
temporal al índice nuevo: su aporte en el mismo bloque es aproximadamente 3 pp.

Deuda almacenada del mercado: **928,172.062478 USDG**. Deuda devengada de las
cuentas observadas: **187,869.914595–187,870.226522 USDG**. Son obligaciones de
los prestatarios; no son excedente capturable ni ingresos. El menor margen de
salud fue 765/764/764 bps, por encima del umbral de señal de 100 bps.
Las seis cuentas sin deuda se conservaron.

Los registros fuente y sus eventos/cabeceras quedaron intactos. La unión solo
reconstruye enlaces de tramos en una copia. No se demuestra historia completa
desde el nacimiento del mercado, ni ausencia de oportunidades en la deuda omitida.

## Tiempo hasta disponer de estado verificado

Se reutiliza la lectura única de PR13, fijada por hash, sin repetir batch. Este
ensayo no es una comparación controlada de velocidad contra PR13: cambian
cohorte, bloque, momento y carga. No se atribuye la variación a una causa aislada.

| Bloque | Entradas, s | Desde recibir cabecera hasta verificación, s | Desde iniciar petición de cabecera hasta verificación, s |
| --- | ---: | ---: | ---: |
| 89,902,767 | 5.350 | 10.276 | 13.756 |
| 89,902,911 | 4.602 | 11.350 | 15.815 |
| 89,903,076 | 3.351 | 6.988 | 11.317 |

La verificación incluye la comprobación canónica posterior y el registro de la
lectura. El tiempo de entradas la excluye. Ninguno incluye simulación de una
ruta, envío o inclusión. **El acceso medido no cumple el objetivo supuesto de
un segundo**, incluso antes de esos pasos comerciales adicionales.

La mediana HTTP fue 2.901 s, con rango 2.306–6.742 s. No se separaron transporte,
conexión, caché o procesamiento del nodo. Tres estados de la misma cohorte no
definen una distribución de producción ni un SLA. Quedan 570/714/879 bloques
posteriores al checkpoint sin indexar en cada observación, explícitamente fuera
de la cobertura del registro.

## Corrección del auditor

Se reprodujo el fallo anterior: si la captura se interrumpía después de unir
historia y antes de comenzar la actualización reciente, el auditor comparaba
el estado unido contra `older-registry.json` y rechazaba una captura parcial
válida con `PERSISTED_REGISTRY_DIFFERS`.

`audit_continuation.py` conserva una fase de unión y el nombre del archivo
persistido correspondiente. Maneja interrupciones antes de la primera petición,
fallos iniciales de cadena, presupuestos agotados y errores de transporte sin
inventar un estado completo. Un checkpoint cambiado invalida la copia y se
vincula a la respuesta original. La ausencia de un ledger no se acepta cuando
el terminal declara solicitudes. No se suprimen controles de hashes o métricas.

Las pruebas inyectan un error RPC en **cada una de las 38 peticiones de una
ejecución sintética**; todos los casos se reconstruyen como detenidos, conservan
lo ya validado y no reintentan. También cubren HTTP 429, JSON malformado, reorgs,
alteración del registro, alteración de tiempos y cadena incorrecta. La regresión
reconstruye exactamente todas las métricas guardadas del piloto real de PR13.
No es una afirmación de cobertura exhaustiva de cualquier fallo de disco o proceso.

## Validación y continuidad

**64 pruebas Python aprobadas:** 14 nuevas, 16 de PR13, 25 del registro y nueve
de aislamiento. Se verificaron 377 blobs originales, 106 workflows deshabilitados
y cero activos. Solidity y Rust no cambiaron ni se repitieron sus suites. El
bytecode de lectura está fijado por los hashes heredados y el manifiesto nuevo.

Desde la raíz, sin consultas remotas:

```bash
python -m unittest discover -s migration/robinhood-history-continuation-20261016T0715 -p 'test_continuation.py' -v
python migration/robinhood-history-continuation-20261016T0715/audit_continuation.py \
  migration/robinhood-history-continuation-20261016T0715/evidence/pilot --out /tmp/nqc-continuation-audit.json
python migration/robinhood-history-continuation-20261016T0715/summarize.py \
  migration/robinhood-history-continuation-20261016T0715/evidence/pilot --out /tmp/nqc-continuation-summary.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

La captura usó `run_continuation.py --out DIRECTORIO_NUEVO --registration-commit
5bfbad3898d1f2b97554c2485340ef5a007d8e95`. Su ventana es fija: repetirla no avanza
el historial. Otro intervalo exige política y fuentes publicadas previamente.
`summarize.py` se añadió después del registro y solo presenta datos ya auditados.
`MANIFEST.sha256` y `evidence/provenance.json` vinculan el paquete.

El próximo ensayo debe aislar el efecto de reutilizar conexiones en la latencia,
con el mismo endpoint, reglas previas y lecturas pareadas del mismo estado.
También permanece pendiente incorporar la historia anterior al bloque 88,646,281.
La financiación del patrocinio, admisión del bundler y captura prospectiva del
ciclo AA/Nitro/DA siguen sin demostrarse. Este ensayo no ejecutó rutas ni
transacciones, no comprometió fondos y no generó ingresos.

Confianza: alta en la corrección reproducida y los cálculos del paquete; limitada
para extrapolar al mercado, porque solo hay un proveedor y tres bloques de una
cohorte parcial, sin pruebas criptográficas independientes de estado o logs.
