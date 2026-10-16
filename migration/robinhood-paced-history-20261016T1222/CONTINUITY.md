# Relevo: historia ampliada con frecuencia global

## Estado final del incremento

Captura TERMINADA, una sola ejecución real. No relanzar `history_acquisition.py` con este protocolo ni sustituir `evidence/pilot`. Base PR18 `9063049967530a682d28d94af5ff17cf46c7bd66`; rama de trabajo/publicación `nqc/paced-history-20261016T1222`.

Protocolo publicado ANTES de RPC: `91b61a95541e5950772a7c919060df3a477d6821`, árbol `f3049191f240e002a372f08ce68f30737861af42`, rama `nqc/paced-history-protocol-20261016T1222`. Las 67 fuentes fijadas siguen intactas. README, resumen y pruebas de informe se añadieron después, sin modificar selección, runner, reglas o capturas.

Captura 16/oct/2026 12:32:06.107286–12:33:18.985806 UTC: 194 métodos RPC/194 HTTP, cero errores, salida 0, journal 72.878522032 s y proceso 72.887374589 s. Un único gate de 350 ms/sesión/presupuesto entre fases, 45.936183325 s de esperas incluidas, mínimo despacho 350.155201 ms. 185 consultas de preparación y nueve de observación. Ningún RPC adicional en esta ejecución.

Se añadieron 400000 bloques históricos 88246281–88646280 (30 Borrow, 13 cuentas nuevas) y cola 90037170–90080877 (43708 bloques, seis Borrow, dos nuevas). Acumulado 1834597 bloques sin huecos, 97 Borrow, 46 cuentas, todas conservadas. Se validó/authenticó target antes de congelar. Se conserva original PR18 y estado antes de catch-up; solo se recalcula el enlace de los segmentos al unir, no sus datos de eventos/checkpoints.

Tres bloques actuales fijados por hash: 90081042, 90081053 y 90081064. 39 cuentas con deuda/siete sin deuda; cobertura 23.8119790010%, falta 76.1880209990%; cero candidatos/cuentas calculadas como liquidables SOLO en esta muestra. La cohorte previa cubre 20.6888815586% en estos mismos hashes; aporte histórico 2.9052802626 puntos, cola 0.2178171798. No atribuir toda variación respecto a muestras anteriores a cuentas nuevas. Tail aún no indexado durante observación 165–187 bloques.

Primaria completa desde ANTES de admisión: 929.916545/1107.512698/1050.535422 ms, mediana 1050.535422, 1/3 ≤1 s. Secundaria desde despacho 753.121766–814.129677 ms; no sustituye primaria. Dos intervalos entre despachos de cabecera 1051.115938/1052.184472 ms, admisiones 934.161995/1109.527449 ms. Muestra muy pequeña de cobertura, no benchmark nuevo. Nueve reutilizaciones del socket cliente de observación; misma conexión que preparación, no adquisición fría medida, ni prueba de backend/SLA/cuota futura. No ruta/envío/inclusión/gas/AA/Nitro/DA/financiación/ingresos.

## Fuente real más reciente

`migration/robinhood-paced-history-20261016T1222/evidence/pilot/registry.json`

- Raíz SHA256 `e9dfe58703e31d07eb8a61be6ee46f62d5b13679c7e78feb286ce47e4d88ceca`.
- SHA256 archivo `8cbbeac9381cfdb0a011bd5a74a06c80b07cc755e999b50b42e920dbe0a05dba`.
- Estado `valid_prefix`, intervalo 88246281–90080877, target completo/autenticado, cohorte congelada para aquella captura.
- Siguiente cola desde 90080878, con checkpoint/inicio y anchor vigente revalidados.
- Siguiente historia contigua 87846281–88246280 (400000 bloques), NO repetir 88246281–88646280.
- Nunca usar registros `evidence/synthetic/` como fuentes reales.

## Pruebas realmente ejecutadas

103 pruebas Python distintas: 96 antes (10 flujo nuevo, 22 paced, 14 continuación, 16 lens/merge, 25 registry, nueve aislamiento) y siete nuevas del informe después. El informe se comprobó dos veces, no se cuentan repeticiones. Fallo sintético en 43 fronteras RPC, cortes HTTP/JSON/RPC después de unir y antes de catch-up, presupuesto global entre fases, reorgs y archivos parciales. Dos trazas artificiales conservadas y claramente separadas.

Replay real exacto aprobado: requests, journal, admisiones y cuatro archivos de estado. Seis manifiestos PR13–PR18 intactos (210/175/77/38/147/114 archivos). 377 blobs originales intactos; 106 workflows deshabilitados, cero activos. Rust/Solidity no cambiaron y no se ejecutaron. Sin trading/firmas/transacciones/despliegues/gastos.

## Comandos

Worktree `/workspace/scratch/f9e56e91df85/nqc-paced-history`. Python 3.12.14. Dependencias exactas PR15 en `/workspace/scratch/f9e56e91df85/nqc-http-deps`; conservar `PYTHONPATH` y `PYTHONDONTWRITEBYTECODE=1` al ejecutar. No alterar proxy/no_proxy/CA/TLS. APIs existentes, sin dependencias/API nuevas en este incremento.

Preparación YA EJECUTADA antes de captura; no regenerar policy/lock ni volver a correr preflight sobre un piloto existente:

```sh
python migration/robinhood-paced-history-20261016T1222/verify_offline.py
python migration/robinhood-paced-history-20261016T1222/offline_evidence.py
```

Captura YA EJECUTADA una vez, comando archivado para trazabilidad, NO para relanzarlo:

```sh
python migration/robinhood-paced-history-20261016T1222/history_acquisition.py --out migration/robinhood-paced-history-20261016T1222/evidence/pilot --registration-commit 91b61a95541e5950772a7c919060df3a477d6821
```

Comprobación offline sin nuevas consultas:

```sh
python migration/robinhood-paced-history-20261016T1222/audit_history.py migration/robinhood-paced-history-20261016T1222/evidence/pilot --out /tmp/nqc-history-audit.json
python -m unittest discover -s migration/robinhood-paced-history-20261016T1222 -p test_report.py -v
```

`summarize.py` y `verify_result.py` produjeron los recibos después de capturar. `MANIFEST.sha256` fija las respuestas y archivos finales; los hashes de fuentes se verifican además contra el protocolo publicado.

## Siguiente incremento acotado

Buscar primero PR/commits posteriores y procesos/capturas en curso. Si no avanzaron, preparar y publicar OTRO protocolo para 87846281–88246280 usando esta fuente, revalidando fronteras, uniendo sin huecos, actualizando solo cola y congelando después del target/auth. Reutilizar helpers y pruebas ya comprobados, no rehacer benchmarks de transporte/gate ni corregir auditores sin defecto nuevo demostrado. Misma selección independiente de salud/liquidaciones y todas las cuentas, incluidas cero deuda. Un único presupuesto/gate de 512 métodos/900 segundos/350 ms, con todas las fases y esperas, sin reset. Probar lo que cambie offline y publicar código/reglas/hashes antes de consultar.

Solo endpoint `https://docs-demo.robinhood-mainnet.quiknode.pro/`. Sin reintentos/redirecciones/HTTP paralelo/sesiones de rescate/cambio de endpoint. Cualquier nuevo error o denegación detiene toda la ejecución y conserva prefijo; no reemplazar captura. El 429 histórico PR16 sigue intacto; un rechazo transitorio no justifica por sí solo desactivar continuidad.

Cuando haya candidatos nuevos, evaluar supervivencia y ciclo completo AA/EntryPoint/bundler/paymaster/Nitro/DA, incluyendo fallos, costes y patrocinio prepagado viable. Captura repetible rentable, admisión comercial y financiación siguen pendientes. Deuda/simulación no son beneficio. Confianza técnica alta en esta muestra auditada; capacidad comercial todavía no probada.
