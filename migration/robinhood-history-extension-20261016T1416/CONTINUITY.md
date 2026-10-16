# Relevo: parada local por capacidad acumulada de eventos

Captura TERMINADA CON PARADA. No relanzar `continue_history.py`, modificar policy/lock/fuentes registradas o sustituir `evidence/pilot`. Base PR20 `976aecb3e25118b1531772d7778668ee34b97d61`; rama `nqc/history-extension-20261016T1416`. Protocolo publicado ANTES de RPC `1d7a779b4d21921bc2f446b6e3fc34bf98132187`, árbol `ab2dbbfe3fb897f2c9f862eb9763919d9bc6281e`, rama `nqc/history-protocol-20261016T1416`.85 fuentes intactas.

## Resultado y causa precisa

16/oct/2026 14:18:27.483494–14:19:23.811698 UTC:145RPC/145HTTP,56.328205968s journal/56.346451685s proceso, salida1, `REGISTRY_CAPACITY_NO_TRIMMING`. Todos HTTP200, cero errores RPC; UNA parada local antes de persistir unión. Tres verificaciones iniciales/142 consultas historia; última `history-anchor-after-index`. Esperas35.482757769s incluidas, gate mínimo350.154858ms. Sin retries, rescate, cambio de proveedor/límite o más RPC.

Historia87446281–87846280 completa en older-registry.json:400000bloques,20Borrow/20bloques con eventos,11cuentas,dos nuevas frente a fuente. Principal registry.json permanece EXACTAMENTE fuente PR20:87846281–90109721,2263441bloques,125Borrow/125bloques con eventos,52cuentas. No merged-before-catchup.json/cohort.json. No catch-up/auth/observaciones actuales:0/3. No cobertura/candidatos/latencia completa actual medidos. No convertir ausencia de observación en cero candidatos ni afirmar nueva rentabilidad.

Unión propuesta (NO persistida):145Borrow/145bloques con eventos/54cuentas. Límite excedido: max_event_blocks128, NO max_borrowers64 ni max_logs512. Primer rechazo al anexar segmento fuente89696281–89706280:128→129bloques con eventos,49cuentas. La primera actualización verbal atribuyó a cuentas; se corrigió después con diagnóstico exacto offline. `registry.validate` utiliza un mensaje genérico para tres límites; max_event_blocks también se usa por respuesta/segmento en enrollment. No cambiar retrospectivamente el protocolo para hacerlo pasar.

## DOS fuentes reales que debe consumir la recuperación

1. `migration/robinhood-history-extension-20261016T1416/evidence/pilot/registry.json` (idéntico PR20/source-registry.json). Raíz `c6b124c940c29d2a876e9d3efdafaf6c678e5654aa1cabcdb2de1309fd4e1a86`; SHA archivo `915da8d32ebea82d9999f23a827a934faa6daef0c105eeeaceb6208fbd58ba5f`. valid_prefix87846281–90109721.
2. `migration/robinhood-history-extension-20261016T1416/evidence/pilot/older-registry.json`. Raíz `1c2ef15961ad7d1d3552afad9eee4aaeb8cabaf54e62b92e9e2c56477f675076`; SHA archivo `83e307af76b631167350471366ac9d44713a9ecbd21613150bca3411745abceb`. valid_prefix87446281–87846280,40segmentos completos,anchor comprobado durante captura.

Conservar ambos y revalidar canon en una ejecución futura antes de unir. No elegir solo registry.json y perder historia guardada, NO reescanear87446281–87846280. Próxima cola desde90109722. Historia aún anterior87046281–87446280 queda para DESPUÉS de recuperar unión+cola bajo un protocolo distinto; no avanzar esa frontera ahora.

## Siguiente incremento técnico

Buscar PR/commits posteriores/procesos/capturas primero. Implementar en archivos nuevos la separación entre capacidad acumulada del registro y límite por respuesta/segmento. Propuesta a probar: max_registry_event_blocks256 acumulados, conservar max_event_blocks128 por segmento, max_logs512, max_borrowers64 y RPC/bytes/tiempo/gate intactos. Es una propuesta, NO política ya publicada ni licencia para modificar PR21. Probar fronteras128/129/256/257, rechazo por cuentas/logs, ausencia de recortes y conservación tras unión/antes de catch-up. Reutilizar helpers, no alterar originales ni reimplementar transporte sin defecto.

Publicar código/reglas/hashes/protocolo NUEVO ANTES de RPC: cargar ambas fuentes por hash, revalidar inicio/checkpoints/frontera canónica, unir sin huecos, conservar estado pre-catch-up, actualizar SOLO cola desde90109722 a anchor vigente buffer64, autenticar target y congelar todas las cuentas antes de tres lecturas fijadas por hash. Nada de selección por salud/liquidaciones ni descarte de deuda cero. No repetir mains de ventanas anteriores. Conservar cualquier nueva parada, no aumentar cotas tras verla en esa ejecución.

Un único presupuesto512métodos/900s con preparación/esperas y gate350ms entre despachos locales, sin reset entre fases/conexiones. Endpoint único https://docs-demo.robinhood-mainnet.quiknode.pro/. Mantener TLS/proxy/no_proxy/CA/timeout/cuerpos. Sin retries/redirecciones/HTTP paralelo/rescate/alternativa tras rechazo. Error/429/denegación detiene TODO. No cambiar red ni mostrar URLs privadas/credenciales.

## Evidencia y pruebas

43 pruebas Python distintas:32antes(6adaptadas+10motor+7informePR20+9aislamiento),7informe nuevo,4diagnóstico capacidad. Repeticiones no se suman. Replay real exacto aprobado, con presencia/bytes de archivos parciales. capacity_diagnosis.py reproduce primer fallo offline sin cambiar límites, sin guardar unión provisional ni consultar RPC.85 fuentes fijadas intactas; ocho manifiestos PR13–PR20 (210/175/77/38/147/114/308/216).377blobs originales,106workflows deshabilitados,ceroactivos. Rust/Solidity no cambiaron/no ejecutados. Ninguna API/dependencia nueva.

Worktree `/workspace/scratch/f9e56e91df85/nqc-history-extension-1416`; Python3.12.14; deps PR15 `/workspace/scratch/f9e56e91df85/nqc-http-deps` vía PYTHONPATH; PYTHONDONTWRITEBYTECODE=1. Pruebas previas verify_offline.py YA EJECUTADAS; no regenerar policy/lock ni preflight sobre piloto existente.

Comando de captura YA EJECUTADO UNA VEZ, únicamente trazabilidad, NO relanzar:

```sh
python migration/robinhood-history-extension-20261016T1416/continue_history.py --out migration/robinhood-history-extension-20261016T1416/evidence/pilot --registration-commit 1d7a779b4d21921bc2f446b6e3fc34bf98132187
```

Replay y tests offline, sin nuevos RPC:

```sh
python migration/robinhood-history-extension-20261016T1416/audit_extension.py migration/robinhood-history-extension-20261016T1416/evidence/pilot --out /tmp/nqc-capacity-audit.json
python -m unittest discover -s migration/robinhood-history-extension-20261016T1416 -p test_capacity.py -v
python -m unittest discover -s migration/robinhood-history-extension-20261016T1416 -p test_report.py -v
```

Resultados en evidence/audit.json,summary.json,capacity-diagnosis.json,process-receipt.json,verification/ y respuestas originales; MANIFEST.sha256 fija archivos finales. No trading/firmas/transacciones/gastos/suscripciones/despliegues; no tocar nexus-engine,Cano,clientes,dominios; workflows deshabilitados. Confianza alta en diagnóstico/preservación, rentabilidad/financiación/AA/Nitro/DA aún sin demostrar. Cerrar esta captura no completa objetivo comercial; no desactivar continuidad por esta parada técnica recuperable.
