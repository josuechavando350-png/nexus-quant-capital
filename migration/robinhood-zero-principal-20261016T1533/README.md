# NQC: prueba de principal cero y atribución de pérdidas

**Resultado: en una simulación histórica ya existente la ruta no necesita inventario
inicial de tokens del ejecutor/router. La financiación comercial del gas sigue sin
probarse.** Incremento offline del 16/oct/2026, basado en PR22
`0fe92f34c863feba59a674c561fa6ebea80c278b`. Cero métodos RPC nuevos, cero segundos de
captura, cero transacciones, firmas, gastos o contactos. No se vuelve a medir ni
se sustituye una captura anterior.

## Qué añade

`principal_audit.py` autentica 251 archivos anteriores y ejecuta los auditores
existentes de estado real y ventana. Añade una comprobación cronológica que los
deltas finales por sí solos no proporcionan: seis lecturas de saldo inicial cero,
ocho balances acumulados por token/dirección, transferencia de colateral antes del
callback, venta dentro de éste, aprobación exacta y cobro de deuda después.
Cada balance acumulado exige cero adelanto y saldo final cero. Las dos series
executor NET/sNET no tienen movimientos; no se inventan lecturas iniciales para ellas.

La traza contiene una llamada de ejecución a `Morpho.liquidate` y cinco STATICCALLs
adicionales a Morpho con selector `0x5c60e39a`; se conservan y no se interpretan como
préstamos. No se invoca un `flashLoan` Morpho separado en esta ruta. El informe
conserva los flujos y sus ordinales completos en `evidence/audit.json`.

| Flujo del caso histórico | Cantidad |
|---|---:|
| Colateral entregado antes del callback | 0.093436250743843184 wsNET |
| Venta → router → ejecutor | 226.094796 USDG |
| Ejecutor devuelve deuda a Morpho | 194.034131 USDG |
| Excedente enviado a la cuenta | 32.060665 USDG |

Se trata del bloque **66744162**, hash
`0x8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7`,
19/sep/2026, estado al índice 1. Es un contrafactual NQC con contratos de cuenta,
ejecutor, router, paymaster y financiación de laboratorio, no beneficio realizado.
Se conserva la autenticación previa de protocolos sin overrides y comparación
local/Nitro. No son pruebas criptográficas de estado ni garantía para cualquier ruta.
USDG no se equipara automáticamente a USD.

## Dónde queda la pérdida

`loss_attribution` separa cuenta del sponsor, pagador/beneficiario del bundler y
entidad consolidada. El débito del sponsor remunera al bundler; sumarlo a la comisión
de red duplica ese traslado interno cuando ambos pertenecen al mismo financiador.

| Caso | Red ETH | Débito sponsor ETH | Ámbito |
|---|---:|---:|---|
| UserOp exitosa | 0.000055018306338 | 0.000076653394686 | Nitro histórico, ventana 31 s |
| UserOp fallida dentro de bundle válido | 0.000039639718050 | 0.000050201161200 | Nitro histórico, variante original en bloque padre |
| Bundle revertido por ventana vencida | 0.000005878984092 | 0 | Nitro histórico, ventana 31 s |
| Rechazo sin envío | 0 | 0 | Definición contable, gastos de servicio desconocidos |

Son casos de variantes/estados distintos, **no una muestra estadística comparable
para estimar probabilidades**. Que EntryPoint no debite al sponsor en un bundle
revertido no significa que el bundler no pierda ETH. Quién refactura esa pérdida
depende de un acuerdo que no existe en esta evidencia. La red incluye movimientos
ArbOS capturados; no se reestimó una componente DA separada ni su precio futuro.

## Modelo condicional de margen

`funding_economics.py` exige los cuatro resultados mutuamente excluyentes: éxito,
UserOp fallida incluida, bundle revertido incluido y rechazo sin envío. No rellena
costes desconocidos con cero; exige probabilidades, precio ETH/USDG, gastos por
resultado, conversión y coste fijo asignado por intento. Diferencia:

- **Operador integrado:** coste nativo = red; sponsor→bundler es interno.
- **Bundler externo:** coste del financiador = débito sponsor + facturas adicionales
  expresas. La red ya pagada por el proveedor no se suma otra vez.

Con `p` de éxito, excedente después de principal `G`, fracción del financiador `s`
y todos los costes esperados `C`, el modelo calcula `EV_financiador = p*s*G − C`.
El umbral `C/(p*s)` es equilibrio; margen positivo exige superarlo. Si `p*s=0`, no
devuelve un umbral finito. La distribución del fundador `(1−s)*p*G` presupone que el
financiador asume los costes y no hay recurso contra el fundador: **ese acuerdo no
está probado**. El reparto se aplica al excedente bruto después de deuda, antes de
gastos; no confundirlo con un contrato de reparto neto.

Las pruebas usan números artificiales y no se ofrecen como pronóstico. No se evalúa
un caso prospectivo de NQC: faltan captura repetible, precios/costes, probabilidades,
cotización del servicio y términos. Ni un EV positivo hipotético financia el primer
intento ni mide riesgo de rachas, solvencia o límite de pérdidas. Reutilizar reservas
finitas y barreras existentes; este modelo no autoriza operaciones.

[PROVIDERS.md](PROVIDERS.md) revisa documentación primaria actual;
[FINANCING.md](FINANCING.md) define evidencia que falta para operar sin aportación
del fundador. Alchemy anuncia soporte Robinhood, pero facturación/créditos no son una
subvención; ZeroDev también describe pagos. Unlinked tiene restricciones diferentes
y no se ha demostrado compatible con esta operación. No hay patrocinador contratado.

## Verificación

**85 pruebas Python distintas aprobadas:** 24 nuevas, 16 replay histórico, 16 ventana,
20 economía anterior y 9 aislamiento. Auditoría offline completa aprobada. Los dos
primeros intentos de la suite nueva tuvieron 2 errores cada uno: el nuevo contador
de llamadas confundió lecturas estáticas adicionales con préstamos y después exigió
calldata sin el argumento final. Se corrigió únicamente el auditor nuevo; ambos logs
fallidos se conservan. Ningún artefacto histórico se alteró.

Se verificaron 18 manifiestos anteriores, 377 blobs originales, 106 workflows
deshabilitados y cero activos; recibos en `evidence/verification`.
Rust/Solidity no cambiaron ni se recompilaron/ejecutaron en este incremento. El replay
offline lee respuestas guardadas; no vuelve a ejecutar EVM ni llama a Robinhood.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s migration/robinhood-zero-principal-20261016T1533 -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python migration/robinhood-zero-principal-20261016T1533/principal_audit.py --out /tmp/nqc-principal-audit.json
```

La salida debe ser nueva; el CLI rechaza sobrescritura. `sources.json` fija entradas;
`MANIFEST.sha256` fija todos los archivos del incremento salvo el propio manifiesto.
