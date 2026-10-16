# Relevo NQC — validación nativa completada, 16/oct/2026

Único repositorio: `josuechavando350-png/nexus-quant-capital`.
PR25: https://github.com/josuechavando350-png/nexus-quant-capital/pull/25 (borrador).
Rama `nqc/native-validation-20261016T1650`. Base PR24
`6c206d67f80db206e1ffb5290e34035d9c1960dc`.
Código/evidencia publicados: `da8a2837c2b9015d0bb5523b1cdc06b8610d4f2e`;
árbol `b781a8d6641f87d8569a77228849e9fcd11980d1`.
Un commit posterior agrega este relevo y actualiza el manifiesto.
Buscar PR/commits posteriores antes de trabajar. Leer AGENTS.md, README y CAPTURE.md.

## Decisión vigente del usuario

Chavando preguntó si seguir o congelar. Se recomendó un presupuesto de **dos
incrementos técnicos sin gasto**: validar la corrección y resolver admisión/
financiación bajo cero capital propio. Aceptó continuar. PR25 completa el primero;
**queda uno**. No reiniciar ese contador por conversación o por otra rama.
Pausar expansión de inventarios/arquitectura que no resuelva esos bloqueos.
Si tras el segundo no se puede probar admisión o la única salida exige dinero/
garantías del usuario, recomendar congelar desarrollo activo, preservando evidencia
y condiciones precisas para retomarlo. No afirmar fracaso económico universal.

## Captura terminada

Protocolo publicado ANTES `4a814940a80d3b5f6effced72984d3ffc53f6f5d`, árbol
`52d88bfe806b4984d3b14e4da079f37bff3ebc2c`, rama fija
`nqc/native-validation-protocol-20261016T1650`. Sus 35 fuentes siguen intactas.
Una captura local 16/oct/2026 16:55:47.080760–16:55:50.559334 UTC:
10 RPC/10 HTTP, proceso 3.481232384 s, salida 0, cero errores inesperados.
0 RPC públicos, 0 transacciones, 0 firmas nuevas. Esperas 1.860784101 s;
gap mínimo 350.112459 ms. Geth cerrado al terminar.
NO ejecutar de nuevo capture_native.py ni sobrescribir evidence/pilot; no alterar
protocolos, locks o código registrado. Próximas mediciones requieren protocolo nuevo.

Seis controles completados, en orden:
1. Firma original, ventana 31 s, stake 0: retorno de validación EVM.
2. Firma alterada a 65 bytes cero: AA23/ECDSAInvalidSignature, antes del paymaster.
3. Firma original, 31 s, stake fixture 1 ETH/delay 86400 s: retorno EVM.
4. Firma original, 1 s, mismo stake fixture: retorno EVM con esa ventana exacta.
5. Depósito cero: AA31 paymaster deposit too low.
6. Presupuesto cero: AA33 reverted, interior BUDGET_POLICY.

Tres positivas recuperan con ecrecover nativo la dirección pública de laboratorio
`0xcf03dd0a894ef79cb5b601a43c4b25e3ae4c67ed`, 3000 gas; negativa también consume
3000 gas pero retorna vacío. AccountValidationData 0 en positivas. El saldo
histórico de la dirección nativa queda en genesis y no en overrides; se conservan
contratos y firma original. Esto corrige la causa observada en PR24, cuyo piloto
fallido permanece intacto. No sustituye lógica nativa ni relaja reglas.

En las tres positivas: prefund 249541240000000 wei, contexto vacío, dos SLOAD y una
SSTORE del presupuesto slot 1. PreOpGas 132658 es validación local, no ciclo completo
ni Nitro/DA/coste comercial. Stake 0/1/1 ETH y depósito 0.1 ETH son fixtures.
Mismo hash/stateRoot local antes/después:
`0x576ad8d0b04db44b548b924210a0d70a6a295b423067a3023b29005b6c2d9350`.

## Pendiente del segundo y último incremento acordado

Resolver o documentar definitivamente el bloqueo de admisión completa del bundler
y la financiación. Leer PR23 FINANCING.md/PROVIDERS.md y evidencia actual, actualizar
sólo hechos necesarios con fuentes primarias. No confundir publicidad de gasless,
depósitos de laboratorio, préstamo de principal o reparto propuesto con un
financiador real que absorba gas/fallos sin recurso contra Chavando.

ValidationManager/parser ERC-7562/depósito agregado/reputación/mempool **no se
ejecutaron**. La instalación anterior de Yarn quedó incompleta por red; revisión
automática rechazó consultar el instalador después de detenerlo. No se retomó en
PR25 y no se instalaron nuevas dependencias. Faltan ethers y otras dependencias.
No reanudar ese instalador ni evadir denegación cambiando proveedor. Sí se puede
inspeccionar read-only si un entorno permitido/caché completo ya está disponible;
si no, registrar capacidad exacta faltante. No usar unsafe o una reimplementación
parcial como prueba de admisión oficial.

Fuente fijada v0.7 leída: STO-031 requiere stake para determinados accesos propios;
ValidationManager exige >30 s restantes y compara con Date.now() del host. La nueva
traza tiene el acceso propio observado, pero el parser no fue ejecutado. Retorno
EVM con stake0/ventana1s no implica aceptación. Fixtures históricos tienen tiempo
19/sep/2026: no sirven como prueba de admisión actual. Cualquier ensayo histórico
debe declarar reloj de laboratorio, sin cambiar reloj de servicios reales ni
desactivar caducidad. Vigencia actual exige nuevo protocolo/fixture explícito.

Probar admisión local tampoco establece condiciones comerciales. No contactar,
firmar, crear cuentas, pagar ni comprometer al usuario sin autorización específica.
Al cerrar ese incremento emitir decisión clara sobre continuidad/congelación y
qué evidencia faltaría para reanudar; no añadir otra expansión de historia.

## Verificación reproducible

48 pruebas Python distintas aprobadas: 14 previas a captura, 5 auditoría nueva,
20 regresiones PR24, 9 aislamiento. Diez fronteras RPC sintéticas interrumpidas en
las pruebas nuevas; límites HTTP/JSON/cuerpos/plazo antes y después de esperar,
gate sin crédito, paradas y verificación de cabecera. No son medidas de Robinhood.
Auditor offline reconstruye exactamente seis resultados y decodifica controles
negativos estrictamente. 20 manifiestos previos, 35 fuentes, 377 blobs originales
intactos; 106 workflows deshabilitados, 0 activos. Sin nuevas pruebas/compilaciones
Solidity/Rust. Manifiesto evidencia 43 archivos; con este relevo 44, excluyéndose
a sí mismo. Logs originales conservan sus espacios finales. Código propio limpio.

Worktree `/workspace/scratch/833721a2e367/nqc-native-validation`, Python 3.12.14.
Sin dependencias nuevas. Geth firmado existente:
`/tmp/nqc-bundler-env-20261016/geth-linux-amd64-1.17.8-a5790770/geth`, SHA256
`d1c45adb02ba6f16f5bc9bd4ae201a702fbdaa236c8065a48fa9f30147c434cd`.
Toolchain y fuentes exactas conservadas en PR24; se reutilizaron sin recompilar.

```sh
PYTHONDONTWRITEBYTECODE=1 python migration/robinhood-native-validation-20261016T1650/audit_native.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s migration/robinhood-native-validation-20261016T1650 -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s migration/robinhood-bundler-validation-20261016T1608 -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s migration -p test_isolation.py -v
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

## Estado económico y límites conservados

No se observaron nuevas oportunidades ni cobertura; ningún ciclo de trading,
AA incluido, Nitro/DA, financiación disponible o ingreso se midió en PR25.
PR23 probó principal cero sólo en un contrafactual histórico específico: venta
226.094796 USDG, repago 194.034131, excedente 32.060665 antes de gastos. No beneficio
real. Fuente del índice sigue PR22:
`migration/robinhood-registry-recovery-20261016T1507/evidence/pilot/registry.json`.
Raíz `c415105959ea642599deccd7ce690b38325e7480351c5082bda4c03d8cd52643`;
SHA archivo `e586db0dff1feaeddcfc12e95f30b1ca2bda6a09bb50a5043f58012c497c4382`.
Prefijo 87446281–90178727; 2732447 bloques, 158 Borrow, 56 cuentas. Cola 90178728;
historia 87046281–87446280, aplazada. Capacidad PR22: 256 bloques de eventos
acumulados, 128 por segmento, 512 logs, 64 cuentas. No volver al límite antiguo128.
PR22 histórico: cobertura26.6934174575%, falta73.3065825425%, cero candidatos sólo
en tres hashes. No son hechos actuales.

Cada futura captura: publicar nuevo código/reglas/hashes ANTES, máximo global
512 métodos/900 s con preparación/esperas, gate350ms sin reset por fases. Error
detiene todo, conserva prefijos/cuerpos; sin retries, redirecciones, HTTP paralelo
o rescate. Único endpoint público autorizado si se necesita en otro protocolo:
https://docs-demo.robinhood-mainnet.quiknode.pro/; TLS/proxy/no_proxy/CA intactos.
Sin firmas nuevas, trading, transacciones, claves reales, gastos, suscripciones,
despliegues, fusiones o workflows activos. No nexus-engine/Cano/clientes/dominios.
Tarea existente pausada: conservar estado/cadencia, no duplicar ni reactivar.
