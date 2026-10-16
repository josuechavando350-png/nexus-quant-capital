# Transporte persistente: mejora real, rentabilidad todavía no demostrada

**La conexión reutilizada leyó las mismas 30 cuentas en 72–316 ms; con estado
verificado, 214–424 ms.** El control anterior tardó 2.39–3.09 s solo en recibir
las entradas. La mejora es importante en esta muestra, pero no acredita todavía
latencia completa menor a un segundo, captura rentable ni disponibilidad comercial.

Captura real del **16/oct/2026, 08:38:26–08:40:21 UTC**, 114.687 s de journal:
49 métodos RPC/49 HTTP secuenciales, 208,663 bytes de cuerpos y cero errores.
Se completaron seis bloques, 18 lecturas de estado y sus 18 comprobaciones
canónicas. En cada bloque hubo igualdad exacta del resultado ABI y del estado
derivado entre los tres modos. No hubo simulación de ruta ni transacciones.

El código, la selección, los seis órdenes y los límites se publicaron antes de
medir, en [8bdd6f8](https://github.com/josuechavando350-png/nexus-quant-capital/commit/8bdd6f8be2cc16ceb6c8330d9186c60cde90c522).
Las fuentes registradas permanecen idénticas. Se mantuvieron los proxies y la
verificación TLS configurados; no hubo reintentos, redirecciones o cambio de endpoint.

## Resultado de transporte

`legacy` es el lector urllib anterior, sin modificar. `fresh` y `persistent`
usan la misma implementación y configuración Requests; cambia si se crea una
sesión por petición o se conserva. El control `fresh` evita atribuir toda mejora
al mero cambio de biblioteca. Orden: L/F/P, F/P/L, P/L/F, P/F/L, F/L/P, L/P/F.
Cada modo ocupa cada posición dos veces. No se eliminaron valores lentos.

| Modo | Lecturas | Entradas: mediana [rango], ms | Estado verificado: mediana [rango], ms |
| --- | ---: | ---: | ---: |
| Anterior, urllib | 6 | 2,643 [2,391–3,095] | 5,263 [5,033–6,998] |
| Requests, sesión nueva | 6 | 2,950 [2,495–8,662] | 5,821 [5,179–13,209] |
| Persistente, primera conexión | 1 | 2,823 | 2,956 |
| Persistente, conexión reutilizada | 5 | 82 [72–316] | 234 [214–424] |

Incluyendo también la primera conexión, las seis lecturas persistentes tienen
medianas de 154.66 ms de entradas y 305.25 ms de estado verificado. El desglose
de primera conexión/reutilización se fijó antes de medir, no para ocultar el
arranque lento. En las cinco parejas reutilizadas, entradas del lector anterior
divididas entre entradas persistentes dan 9.78–34.62; para estado verificado,
15.16–24.44. Son razones observadas, no una garantía de velocidad de producción.

Se observó el mismo objeto socket cliente en las 11 peticiones persistentes
posteriores a la primera. Las 12 peticiones `fresh` abrieron sockets distintos.
El endpoint se accedió por el proxy configurado: esto demuestra reutilización
del socket cliente, **no identifica ni demuestra la conexión interna del nodo**.
Los sockets del lector antiguo no fueron instrumentados.

### Todos los bloques, sin descartar valores

Cada celda muestra entradas / estado verificado, en milisegundos redondeados.
Hashes completos y tiempos sin redondeo están en `evidence/summary.json` y el auditor.

| Bloque | Orden | Anterior | Sesión nueva | Persistente |
| --- | --- | ---: | ---: | ---: |
| 89,942,517 | L/F/P | 2,623 / 5,033 | 3,099 / 5,635 | 2,823 / 2,956 |
| 89,942,776 | F/P/L | 2,502 / 5,235 | 2,495 / 5,179 | 72 / 214 |
| 89,942,908 | P/L/F | 2,663 / 5,291 | 3,509 / 6,053 | 82 / 234 |
| 89,943,045 | P/F/L | 2,391 / 5,054 | 2,692 / 5,984 | 76 / 223 |
| 89,943,178 | F/L/P | 3,095 / 6,427 | 8,662 / 13,209 | 316 / 424 |
| 89,943,406 | L/P/F | 2,868 / 6,998 | 2,801 / 5,658 | 227 / 376 |

Entradas termina al recibir el cuerpo completo, antes de decodificarlo. Estado
verificado termina después de derivar posiciones y comparar correctamente la
cabecera canónica posterior; incluye procesamiento y persistencia intermedios.
El detalle exacto está en `PRE_REGISTER.md`.

**No confundir estos tiempos con detección completa o trading.** La cabecera
inicial de cada bloque siguió llegando mediante el lector anterior. Desde iniciar
esa petición hasta el estado persistente verificado se midieron **2.723–26.398 s**;
los modos posteriores esperan a los anteriores y la primera ronda incluye
autenticación. Estas duraciones no aíslan el transporte. Incluso las dos rondas
con persistente primero siguen incluyendo la conexión inicial lenta de urllib.
Cinco lecturas/verificaciones aisladas cumplieron el supuesto de 1 s; el ciclo
completo desde solicitar cabecera **no**. No se midieron ruta, envío ni inclusión.

## Cohorte y límite comercial

Se conservaron las 30 cuentas de PR14, sin selección por salud o liquidaciones,
incluidas seis sin deuda. No se amplió la historia ni se actualizó la cola: es
deliberadamente una comparación de transporte sobre una cohorte fija, no un nuevo
inventario. El registro sigue cubriendo 88,646,281–89,902,197, 1,255,917 bloques,
57 Borrow; raíz `3b530c3214b58b8ae4adb5dc4aa399b6e2db1994396bb2ce918302cf0a63f8de`.
Se revalidaron sus dos límites antes de congelarlo. Los bloques entre checkpoint
y observación, **40,320–41,209**, no están indexados por este ensayo.

En los seis bloques nuevos:

- 24 cuentas con deuda; cero señales bajo el umbral registrado de 100 bps y cero
  posiciones calculadas como no saludables.
- 175,104,105,238,630,296 borrowShares observadas de 865,114,351,430,594,397 totales:
  **20.2405733935% de cobertura; 79.7594266065% pendiente**.
- 690,010,246,191,964,101 participaciones quedan fuera de la cohorte. La cobertura
  histórica de PR14 no se reutilizó como si fuera un hecho actual: se recalculó.
- Deuda no es beneficio. Captura repetible, margen neto, bundler y patrocinio
  prepagado financiable siguen sin demostrarse. Beneficio realizado permanece null.

## Seguridad operativa y auditoría

El nuevo lector comparte un único presupuesto para todos los modos. Se preservan
respuestas, prefijos devueltos por la biblioteca, errores y ledger; cualquier fallo
detiene el conjunto, sin cambiar proveedor ni repetir rondas. Las excepciones
no imprimen URLs de proxy o credenciales. Ninguna clave o firma fue necesaria.

La auditoría offline reproduce el flujo del programa con las respuestas guardadas,
exige el orden y consultas exactos, reconstruye estado/paridad/tiempos, y verifica
la cadena SHA-256 del journal. No vuelve a consultar la red. Hashes y replay
detectan inconsistencias; no son una prueba criptográfica independiente de que
el proveedor o los relojes externos sean correctos.

**80 pruebas Python aprobadas**: 16 nuevas y 64 de regresión/aislamiento.
Las nuevas incluyen los 49 puntos de fallo RPC sintético, HTTP 302/429/503,
desconexión, JSON, timeout, truncamiento, límite de bytes, proxies/CA/netrc,
presupuestos, fuente alterada, reorg, paridad y corrupción de métricas.
Se verificaron 377 blobs originales, 106 workflows deshabilitados y cero activos;
los manifiestos de PR13 y PR14 también permanecen válidos. Solidity/Rust no
cambiaron ni se volvieron a ejecutar. Las pruebas no cubren todo posible fallo
del sistema operativo, disco o proveedor.

## Reproducción y siguiente paso

Usar Python 3.12 con las dependencias exactas de `requirements.txt`. Desde la raíz:

```bash
python -m unittest discover -s migration/robinhood-transport-benchmark-20261016T0821 -p 'test_*.py' -v
python migration/robinhood-transport-benchmark-20261016T0821/audit_transport.py migration/robinhood-transport-benchmark-20261016T0821/evidence/pilot --out /tmp/nqc-transport-audit.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

La captura ya terminó. No repetir `benchmark.py` como si agregara evidencia
prerregistrada nueva. `summarize.py` y `build_evidence.py` son reporting posterior;
no intervinieron en la selección, orden ni medición. `evidence/provenance.json`
registra el comando real y `MANIFEST.sha256` fija el paquete final.

Próximo incremento: publicar un protocolo nuevo para **cabecera, lectura única
y verificación usando transporte persistente**, con cola actualizada y cohorte
congelada antes de observar, para medir adquisición completa sin la espera
artificial entre controles. Conservar el arranque frío y probar la continuidad
del presupuesto y las paradas. Después ampliar el pasado pendiente y, cuando
aparezcan candidatos nuevos, medir supervivencia y ciclo AA/Nitro/DA con costes.

Confianza técnica alta en la paridad y en la mejora observada en este entorno;
limitada para extrapolar: seis bloques, un proveedor demo y una cohorte parcial.
No es un SLA, una admisión comercial ni evidencia de ingresos.
