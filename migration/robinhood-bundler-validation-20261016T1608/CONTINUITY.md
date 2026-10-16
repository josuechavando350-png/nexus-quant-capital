# Relevo NQC — validación local, 16/oct/2026

Repositorio único: `josuechavando350-png/nexus-quant-capital`.
PR24: https://github.com/josuechavando350-png/nexus-quant-capital/pull/24 (borrador).
Rama `nqc/bundler-admission-20261016T1608`; base PR23
`085c88a20f9b9b0d1cea875833d19e84538b33e6`.
Código/evidencia publicados: `5ee226e90e425225b8647153ae8309b8f64b2974`;
árbol `86afebfa2c76b3d3eafa23856ea6e1619e72d5a4`.
El commit posterior sólo añade este relevo y actualiza el manifiesto.
Buscar primero PR/commits posteriores; leer AGENTS.md, README y CAPTURE.md.

## Resultado cerrado, no relanzar

Una captura con protocolo preregistrado
`dae502a2d0f26ce16a7a9d286ff889fb26d5af42`, árbol
`5cc5a66e2340ccc67bd7bdb04b71668c268a477f`, rama inmutable
`nqc/bundler-validation-protocol-20261016T1608`.
Geth1.17.8 local, collector oficial del bundler v0.7; **no bundler completo**.
4 RPC locales/4 HTTP, 0 públicos, 0 envíos, 1.532053798 s, salida1.
Esperas1.036228139 s; gap mínimo350.150358 ms. Cero errores HTTP/RPC;
una validación EVM intentada, revert inesperado; el runner se detuvo.
0/5 controles completados; paymaster no alcanzado, comprobación final de
cabecera no alcanzada. No afirmar stake observado, aceptación, candidatos o gas.
No sobrescribir `evidence/pilot`, no modificar ni ejecutar de nuevo el runner
registrado, no convertir esta parada en control negativo esperado.

Error decodificado: `FailedOpWithRevert(0,"AA23 reverted",0xf645eedf)`, interior
`ECDSAInvalidSignature()`. La llamada a `0x…01` retorna vacío/gas0; el hash de
UserOperation coincide con el aprobado y calldata/firma pública siguen iguales.
La causa identificada en fuente Geth fijada: todo override de un precompilado
nativo lo elimina de la tabla, incluso sólo saldo/estado vacío. Nuestro adaptador
copió inadvertidamente esa dirección del prestate. No atribuirlo a un rechazo del
paymaster ni a defecto demostrado del contrato en Robinhood.

`audit_stopped.py` autentica respuestas/orden/gate/entradas y reproduce la parada.
Fuente primaria Geth `a579077007b98217c3e253a66e4b452ca0c32b96`,
`internal/ethapi/override/override.go`, blob
`d3644570325c499d40af7006d4e409ab8067476b`, conservada en `evidence/diagnosis`.

## Siguiente incremento concreto

Integrar **en archivos y protocolo nuevos** la propuesta offline `prepare_next.py`:
saldo/nonce pasivos de precompilados Shanghai1–9 en genesis, no en stateOverrides;
preservar firma, UserOp, estado de contratos y todos los demás fixtures. Rechazar
código/almacenamiento no vacío/movimientos/colisiones en esas direcciones. No
sustituir `ecrecover`, no usar validación insegura ni relajar reglas para pasar.
La propuesta está probada offline, pero **no ejecutada en Geth**. Faltan integración,
pruebas de límites/parada del nuevo runner y publicación de reglas/hashes antes
de cualquier nueva medición. Conservar este piloto fallido y sus fuentes.

Después, una nueva captura local de los cinco controles originales (sin stake,
con stake fixture, ventana1s, depósito0, presupuesto0) bajo su nuevo protocolo.
Mantener presupuesto512/900s global, gate350ms, sólo loopback y métodos de lectura,
sin retries/HTTP paralelo/redirecciones ni reinicio tras error. Verificar que la
precompilación nativa esté activa con firma positiva original y un control negativo
de firma, sin firmar de nuevo. Publicar el orden de esos controles antes de medir.
No inferir firma válida sólo de ABI, ni bundler aceptado sólo de EVM exitosa.

Bloqueo independiente: faltan dependencias del bundler completo (`ethers` y otras).
Yarn tuvo cuatro mensajes de reintento, no terminó; proceso ausente al detenerlo.
Revisión automática rechazó consultar la sesión del instalador tras la parada por
riesgo de mantener tráfico. No se reinició, no se cambió proveedor, no se evitó
la restricción. No retomar ese instalador ni evadir la denegación. El código de
trazador autónomo y Geth disponibles bastan para la siguiente prueba local acotada.
Para demostrar admisión completa sigue haciendo falta un entorno permitido con
dependencias fijadas y ejecución real de ValidationManager/parser/mempool. No
presentar reglas leídas o un parser reimplementado como esa ejecución.

Lectura de fuente v0.7: validez restante debe ser estrictamente mayor a30s;
STO-031 impone stake en determinados accesos a almacenamiento propio. Las reglas
no se ejecutaron aquí. Fixtures1ETH/86400s y depósito0.1ETH no son fondos actuales,
cotización ni mínimo comercial. Bundler/financiador externos, términos sin recurso,
gas de fallos, reposición y rentabilidad continúan sin demostrar. Chavando no tiene
capital propio; no crear gastos, cuentas, suscripciones o contactos por inferencia.

## Verificación y reproducción offline

45 pruebas Python distintas aprobadas:14 preparatorias+6 diagnóstico+16window+
9aislamiento. 24 fuentes registradas,19manifiestos previos,377blobs originales
intactos;106workflows deshabilitados,0activos. EntryPointSimulations se compiló;
contratos NQC sin cambios; no suite Solidity/Rust. Geth quedó detenido.
Manifiesto de evidencia54archivos; este relevo aumenta a55, excluyendo el propio
manifiesto. Se excluyen db/clave de nodo y JWT público del proceso local.
`git diff --check` advierte espacios finales en la clave PGP original y logs
originales Geth; se preservan bytes. No advertencias en código propio.

Worktree `/workspace/scratch/833721a2e367/nqc-bundler-admission`, Python3.12.14.
Geth binario `/tmp/nqc-bundler-env-20261016/geth-linux-amd64-1.17.8-a5790770/geth`;
SHA256`d1c45adb02ba6f16f5bc9bd4ae201a702fbdaa236c8065a48fa9f30147c434cd`.
Firma oficial válida, huella`FDE5A1A044FA13D2F7ADA019A61A13569BA28146`.
Primer importPGP falló al arrancar agente, verificación posterior válida; recibos
conservados. No afirmar reproducibilidad del binario. Versiones/hashes en toolchain.

```sh
PYTHONDONTWRITEBYTECODE=1 python migration/robinhood-bundler-validation-20261016T1608/audit_stopped.py
PYTHONDONTWRITEBYTECODE=1 python migration/robinhood-bundler-validation-20261016T1608/prepare_next.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s migration/robinhood-bundler-validation-20261016T1608 -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s migration/robinhood-sponsor-window-20261016 -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s migration -p test_isolation.py -v
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

## Índice real y restricciones sin cambios

Fuente PR22 `migration/robinhood-registry-recovery-20261016T1507/evidence/pilot/registry.json`.
Raíz`c415105959ea642599deccd7ce690b38325e7480351c5082bda4c03d8cd52643`;
SHAarchivo`e586db0dff1feaeddcfc12e95f30b1ca2bda6a09bb50a5043f58012c497c4382`.
Prefijo87446281–90178727;2732447bloques/158Borrow/56cuentas. Cola90178728;
historia87046281–87446280, para protocolo posterior. Usar capacity_registry/tail/
merge PR22,256bloques de eventos acumulados,128por segmento,512logs,64cuentas.
PR22 histórico15:17–15:18UTC:26.6934174575% cobertura,73.3065825425% faltante,
47con deuda/nueve sin deuda,0candidatos sólo en tres hashes. Nada se actualizó aquí.

Único RPC público autorizado, sólo si otro incremento lo requiere:
https://docs-demo.robinhood-mainnet.quiknode.pro/. Conservar TLS/proxy/no_proxy/CA,
límites y endpoint; error/denegación detiene todo, sin proveedor alternativo.
Sin trading, firmas nuevas, envíos, fondos reales, gastos, despliegues, fusiones o
workflows activos. No tocar nexus-engine/Cano/clientes/dominios. Mantener evidencia
negativa y originales. No confundir prueba local, deuda o simulación con ingresos.
Tarea existente pausada: conservar estado/cadencia, no duplicar ni reactivar.
