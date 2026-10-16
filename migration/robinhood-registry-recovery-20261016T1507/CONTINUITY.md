# Relevo: recuperación PR22 completada y restricción sin capital propio

[PR22 borrador](https://github.com/josuechavando350-png/nexus-quant-capital/pull/22), rama `nqc/registry-recovery-20261016T1507`. Buscar primero PR/commits/procesos posteriores. Base PR21 `276883828ef921c4f3b55b3dd5ea395615222c73`. Leer AGENTS.md, README raíz y CAPTURE.md. No fusionar.

Evidencia publicada en commit `e8e36de451ea9ab7a35301dcb2a65cd8d03032a2`, árbol `76ad74d8039da714d705c5de9c45a40c4d207ed0`. [Informe fijado a ese commit](https://github.com/josuechavando350-png/nexus-quant-capital/blob/e8e36de451ea9ab7a35301dcb2a65cd8d03032a2/migration/robinhood-registry-recovery-20261016T1507/CAPTURE.md). Este relevo posterior solo añade las referencias; consultar HEAD final del PR.

Captura única TERMINADA, no relanzar `recovery.py`, sobrescribir `evidence/pilot`, regenerar lock o modificar fuentes registradas. Protocolo previo `1b850c9bb8a31ae5f8f083431c8d822e5419c854`, árbol `2961582b305451dc42ba6a268ebccb32a7d55fee`, rama fija `nqc/recovery-protocol-20261016T1507`. 101 fuentes intactas. README/PROTOCOL describen la preparación inmutable; CAPTURE.md es el resultado posterior.

## Resultado de esta ejecución

16/oct/2026 15:17:38.064878–15:18:04.626210 UTC: 56 métodos RPC/56 HTTP, cero errores, salida 0. Journal 26.561335300 s, runner 26.582011681 s, proceso 26.885143152 s. Cinco verify, cero history, 38 catchup, cuatro authenticate, nueve observe. 12.641461092 s de espera incluidas, gap mínimo 350.167510 ms. Una sesión sin rotación/retry/rescate.

Se recuperaron sin reescanear 400000 bloques 87446281–87846280, 20 Borrow y dos cuentas nuevas de `older-registry` PR21. Cola 90109722–90178727: 69006 bloques, 13 Borrow y dos cuentas nuevas. Acumulado 2732447 bloques contiguos, 158 Borrow, 56 cuentas; target completo/autenticado antes de congelar. Ambas fuentes y estado unido previo a catch-up conservados; payloads de segmentos previos intactos, enlaces SHA reconstruidos.

Bloques 90178936/90178947/90178958: 47 cuentas con deuda, nueve sin deuda, cobertura 26.6934174575%, falta 73.3065825425%, cero candidatos/unhealthy SOLO en esta muestra. Cohorte previa en los mismos hashes 26.2000137557%; dos históricas +0.0726990570 puntos y dos de cola +0.4207046448 puntos. No atribuir todo el avance desde PR20 a esas cuentas. Tail sin indexar 209–231 bloques. Datos históricos de la captura, no estado actual garantizado ni ingresos.

Primaria incluyendo espera antes de cabecera 989.818230/1051.684424/1047.189116 ms; solo 1/3 <=1 s. Secundaria 811.209702–813.570599 ms no sustituye primaria. Despachos de cabecera separados 1051.207691/1050.980720 ms. Admisiones 990.952406/1053.115131 ms; intervalo aislado menor no es cadencia sostenida subsegundo. Nueve reutilizaciones del socket cliente, no backend/SLA/cuota; no adquisición fría completa ni trading/gas/AA/Nitro/DA actuales.

55 pruebas Python distintas (47 antes, ocho informe después), 35 fronteras RPC sintéticas auditadas, replay real exacto. Nueve manifiestos anteriores intactos;377 blobs originales,106 workflows deshabilitados,cero activos. Rust/Solidity sin cambios/no ejecutados.

## Fuente más reciente

`migration/robinhood-registry-recovery-20261016T1507/evidence/pilot/registry.json`

- Raíz `c415105959ea642599deccd7ce690b38325e7480351c5082bda4c03d8cd52643`.
- SHA archivo `e586db0dff1feaeddcfc12e95f30b1ca2bda6a09bb50a5043f58012c497c4382`.
- valid_prefix 87446281–90178727. Próxima cola 90178728; revalidar inicio/checkpoint/anchor vigente antes de continuar.

**Usar `capacity_registry.py`, `tail.py` y `merge.py` nuevos para este registro.** Contiene 158 bloques con eventos y no cabe en el registry antiguo limitado a 128 acumulados. No volver al motor PR19 con su binding viejo, ni ejecutar mains de ventanas antiguas. Nueva cota acumulada 256, por segmento/respuesta128, logs512, cuentas64 (56 usadas). No recortar ni ampliar cotas después de observar un rechazo.

Para ampliar historia bajo otro protocolo: siguiente ventana 87046281–87446280 (400000 bloques). Reutilizar el nuevo registry/updater y helpers puros, todos los inputs por hash, unión sin huecos, catch-up, auth/freeze y reconciliación. No reescanear 87446281–87846280. Si otro incremento avanzó usar su frontera más reciente.

## Prioridad comercial indicada por Chavando

El usuario volvió a indicar que NO tiene capital principal propio. Recuperar el índice no resuelve financiación. Antes de otra ronda de infraestructura sin objetivo económico, revisar la ruta Morpho y evidencia ya existentes para distinguir financiación por callback/préstamo flash según código real, de gas/bundler/paymaster. No suponer que hace falta un préstamo flash separado si el callback existente resuelve el principal, ni presentar un saldo de fixture como dinero disponible.

Incremento recomendado: auditoría acotada y verificable de requisitos para ejecutar sin capital del fundador, partiendo de `robinhood-real-state-replay-20261016`, `robinhood-sponsor-window-20261016`, `robinhood-route-admission-20261016` y `robinhood-aa-20261016/SPONSORSHIP.md`. Distinguir qué ya prueba el caso histórico y qué falta hoy: mecanismo real de principal, cotización/margen prospectivo, admisión exacta del bundler, presupuesto externo prepagado y quién absorbe fallos. Probar offline primero; si requiere nueva medición RPC, publicar un protocolo NUEVO antes. Verificar cualquier API/condición actual en documentación primaria. No repetir simulación histórica como nueva oportunidad ni iniciar contactos, cuentas, gastos o transacciones. Un sponsor no confirmado mantiene el bloqueo comercial, aunque el software funcione. No es necesario esperar un candidato para documentar estas condiciones; medir su ruta rentable sí requiere uno nuevo.

Cuando haya candidatos nuevos: supervivencia y ciclo completo con AA/EntryPoint/bundler/paymaster/Nitro/DA, fallos/costes/reparto, conservando todos los intentos. Captura repetible rentable, financiación y admisión comercial siguen sin demostrar. El objetivo no se completa al terminar un lote.

## Comandos y entorno

Worktree `/workspace/scratch/833721a2e367/nqc-registry-recovery`. Python3.12.14; dependencias exactas PR15 en `/workspace/scratch/f9e56e91df85/nqc-http-deps` vía PYTHONPATH; PYTHONDONTWRITEBYTECODE=1. No nuevas dependencias/APIs.

YA EJECUTADO UNA VEZ, solo trazabilidad, NO relanzar:

```sh
python migration/robinhood-registry-recovery-20261016T1507/recovery.py --out migration/robinhood-registry-recovery-20261016T1507/evidence/pilot --registration-commit 1b850c9bb8a31ae5f8f083431c8d822e5419c854
```

Revisión offline reproducible:

```sh
python -m unittest discover -s migration/robinhood-registry-recovery-20261016T1507 -p test_recovery.py -v
python -m unittest discover -s migration/robinhood-registry-recovery-20261016T1507 -p test_report.py -v
python migration/robinhood-registry-recovery-20261016T1507/audit_recovery.py migration/robinhood-registry-recovery-20261016T1507/evidence/pilot --out /tmp/nqc-recovery-audit.json
```

No regenerar policy/lock ni rerun de generador sintético sobre carpetas existentes. `verify_offline.py` comprueba ausencia de piloto y ya terminó antes de captura. Recibos en evidence/verification; resultados en audit.json/summary.json/process-receipt.json; MANIFEST fija archivos finales.

## Límites persistentes

Endpoint único https://docs-demo.robinhood-mainnet.quiknode.pro/. Por ejecución global512 métodos/900s incluyendo preparación/esperas, gate350ms. TLS/proxy/no_proxy/CA/timeouts/bytes intactos. Sin retries/redirecciones/HTTP paralelo/rescate/alternativa para saltar denegaciones. Error/429/denegación detiene TODO. No modificar red ni mostrar credenciales/URLs privadas. Conservar negativos y prefijos. Código/reglas/hashes antes de medir; rama/PR borrador material, nunca merge automático.

Solo nexus-quant-capital. Sin trading/firmas/transacciones/claves/gastos/suscripciones/despliegues. No tocar nexus-engine,Cano,clientes,dominios. Conservar originales/workflows deshabilitados. No afirmar pruebas/capturas no realizadas ni funcionamiento futuro garantizado. Evitar trabajo duplicado. Al consultar el estado de la tarea existente en esta sesión aparecía deshabilitada; se conservó ese estado, sin atribuirlo a fallo ni reactivarla.
