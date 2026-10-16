# Relevo: extensión histórica 20261016T1317

Captura TERMINADA. No relanzar `continue_history.py` ni sobrescribir `evidence/pilot`, no modificar policy/lock/protocolo ya registrados. Base PR19 `ca184cdd14d8d5a8a4d447a9723a0e792dc00132`; rama nueva `nqc/history-extension-20261016T1317`.

Publicado en [PR20 borrador](https://github.com/josuechavando350-png/nexus-quant-capital/pull/20). Commit de evidencia `bb9cd2f930a7615c3c3b57e9b6df2b8f5e7620d4`, árbol `5ec82e413daa1b4179832e3ba9ccbbbe90c0d7fa`. El relevo posterior solo añade esta referencia; consultar HEAD final en GitHub. No fusionar automáticamente.

Protocolo ANTES de RPC `c0fc579e3ec4ea68dcf5c77c4dc6c3d40333bd94`, árbol `d686f2f3286cf9fd2ec5d95189d5139558f65fcf`, rama `nqc/history-extension-protocol-20261016T1317`. 76 fuentes fijadas intactas. Motor PR19 reutilizado sin cambios; adaptador carga nueva política y auditor la recibe explícitamente. No ejecutar mains antiguos con sus ventanas previas.

## Resultado real

16/oct/2026 13:20:32.903052–13:21:47.168513UTC,180RPC/180HTTP,74.265462399s journal/74.281850080s proceso, salida0,cero errores.171preparación+9observación. Una sesión/gate/presupuesto global; esperas43.572649098s incluidas, gapmínimo350.148641ms. La primera petición de preparación tardó9.992s, preservada. Ningún otro RPC en esta ejecución, ningún retry.

Historia87846281–88246280:400000bloques,25Borrow,cinco cuentas nuevas; cola90080878–90109721:28844bloques,tresBorrow,una nueva. Total2263441bloques contiguos,125Borrow,52cuentas. Fuente, registro histórico separado y estado unido antes de catch-up conservados. Eventos/checkpoints previos intactos; enlaces SHA reconstruidos al unir, no afirmar identidad byte a byte de enlaces. Target completo/autenticado antes de congelar; límite64 no se alcanzó ni cambió.

Tres hashes/bloques90109855/90109865/90109876:41cuentas con deuda/11sin deuda; cobertura24.8972889661%, falta75.1027110339%; cero candidatos/cuentas calculadas como liquidables SOLO en muestra. Cohorte previa cubre23.8713121115% en mismos hashes; nuevas históricas+0.5190967695puntos y nueva de cola+0.5068800851. De las cinco históricas nuevas, una tenía deuda y cuatro no; conservar todas. No atribuir toda diferencia frente al23.8120% histórico PR19 a descubrimientos. Tail sin indexar134–155bloques durante observación. No hechos actuales garantizados ni ausencia universal de oportunidades.

Primaria completa ANTES de admisión936.004229/1109.214298/1051.182297ms,mediana1051.182297,1/3≤1000. Secundaria desde despacho751.384596–813.684149ms NO sustituye primaria. Despachos de cabecera separados1051.539110/1051.215917ms; admisiones939.034326/1110.842186ms. Un intervalo aislado menor no prueba cadencia sostenida subsegundo. Solo tres lecturas de cobertura, sin adquisición fría de observación ni benchmark nuevo. Nueve reutilizaciones socket cliente; no backend/SLA/cuota futura. Sin ruta/envío/inclusión/gas/AA/Nitro/DA/bundler/patrocinio/ingresos medidos.

## Fuente real más reciente

`migration/robinhood-history-extension-20261016T1317/evidence/pilot/registry.json`

- Raíz `c6b124c940c29d2a876e9d3efdafaf6c678e5654aa1cabcdb2de1309fd4e1a86`.
- SHA archivo `915da8d32ebea82d9999f23a827a934faa6daef0c105eeeaceb6208fbd58ba5f`.
- `valid_prefix`,87846281–90109721,target completo.
- Próxima cola90109722; revalidar checkpoint/inicio/anchor vigente.
- Siguiente historia400000bloques87446281–87846280. No repetir ventanas anteriores ni usar synthetic como fuente.

## Verificación realmente ejecutada

39pruebas Python distintas:32antes(seis extensión+10historia+7informe previo+9aislamiento),siete informe nuevo después. Las siete nuevas se ejecutaron dos veces al añadir atribución de deudores; no contar repeticiones. Regresiones reutilizadas cubren43fronteras RPC sintéticas y paradas tras unión/antes de catch-up, sin reimplementar lo ya hecho. Replay real exacto aprobado, cuatro archivos de estado reproducidos.

76fuentes intactas; siete manifiestos PR13–PR19 intactos(210/175/77/38/147/114/308archivos).377blobs originales,106workflows deshabilitados,ceroactivos. Rust/Solidity no cambiaron/no ejecutados. Adaptadores usan APIs Python ya empleadas y transporte heredado; ninguna dependencia/API nueva.

## Comandos y entorno

Worktree `/workspace/scratch/f9e56e91df85/nqc-history-extension`; Python3.12.14; dependencias exactas PR15 en `/workspace/scratch/f9e56e91df85/nqc-http-deps` mediante PYTHONPATH. Usar PYTHONDONTWRITEBYTECODE=1. Mantener TLS/proxy/no_proxy/CA y límites de cuerpos/timeout.

Pruebas previas YA EJECUTADAS; no regenerar política/lock ni preflight sobre piloto existente:

```sh
python migration/robinhood-history-extension-20261016T1317/verify_offline.py
```

Captura YA EJECUTADA UNA VEZ, solo trazabilidad, NO relanzar:

```sh
python migration/robinhood-history-extension-20261016T1317/continue_history.py --out migration/robinhood-history-extension-20261016T1317/evidence/pilot --registration-commit c0fc579e3ec4ea68dcf5c77c4dc6c3d40333bd94
```

Replay offline permitido sin RPC:

```sh
python migration/robinhood-history-extension-20261016T1317/audit_extension.py migration/robinhood-history-extension-20261016T1317/evidence/pilot --out /tmp/nqc-extension-audit.json
python -m unittest discover -s migration/robinhood-history-extension-20261016T1317 -p test_report.py -v
```

`summarize.py` y `verify_result.py` generaron resultados/recibos posteriores sin alterar protocolo. Manifest final fija respuestas y archivos. Publicar/consultar cabeza final en GitHub antes de seguir; no fusionar.

## Siguiente incremento

Buscar PR/commits/procesos posteriores primero. Si no avanzó, nuevo protocolo para87446281–87846280 con esta fuente; conservar cuentas/canon/fuentes/segmentos, unir sin huecos, actualizar solo cola y congelar tras target completo/auth. Selección independiente de salud/liquidaciones. Reutilizar motor/adaptadores ya probados, no rehacer transporte/gate/auditor salvo defecto nuevo. Si el límite64 impide ampliar, conservar prefijo y preparar capacidad mayor bajo otro protocolo probado; no recortar cuentas ni cambiar límites retroactivamente.

Offline primero y publicar reglas/código/hashes ANTES de toda medición. Único endpoint `https://docs-demo.robinhood-mainnet.quiknode.pro/`.512métodos/900s TOTAL con preparación/esperas, gate350ms sin reset. No retries/redirecciones/paralelismo HTTP/sesión de rescate/proveedor alternativo. Error/429/denegación detiene TODO y conserva evidencia; nunca sustituir captura. Limitación transitoria no basta por sí sola para desactivar continuidad.

Cuando haya candidatos, estudiar supervivencia y ciclo AA/EntryPoint/bundler/paymaster/Nitro/DA con fallos/costes y patrocinio prepagado viable. No trading/firmas/transacciones/gastos/suscripciones/despliegues. No tocar nexus-engine,Cano,clientes,dominios. Captura repetible rentable, admisión comercial y financiación siguen pendientes. Confianza técnica alta en esta muestra auditada, comercial insuficiente; deuda o simulación no son beneficio.
