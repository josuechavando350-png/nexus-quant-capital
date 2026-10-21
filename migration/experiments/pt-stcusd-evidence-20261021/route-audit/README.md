# PT-stcUSD: canje con retiro de un segundo mercado Morpho

21-oct-2026. Continuacion de `1461531e348b0427c88718c23c675005db021a57`. Solo investigacion offline; no modifica el ejecutor NQC ni activa workflows.

## Hallazgo

La liquidacion Ethereum `0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2`, bloque 25666958, indice 0, incluye un canje Pendle `RedeemPyToToken`. Se recuperaron las seis paginas de eventos indexados, indices 0-52, con paginacion final nula. No se recupero la traza completa ni se ejecuto EVM.

El canje obtiene 3305.262344 USDC retirandolos del mercado Morpho `0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64`, etiquetado cbBTC/USDC en el catalogo anterior. Sus parametros producen ese identificador por hash. NO es el mercado PT liquidado `0x03f715ef1ae508ab3e1faf4dffdbf2a077d1f0ad10c5aad42cf4438d5e3328af`.

La secuencia de transferencias USDC es Morpho -> adaptador -> boveda -> estrategia -> reserva -> cUSD -> SY -> ejecutor (eventos 20,22,25,28,32,35,37). Es el mismo dinero pasando por siete cuentas, no siete ingresos. El ejecutor devuelve 3220.954251 USDC a Morpho en el evento 42. Morpho pierde netamente 84.308093 USDC en estos movimientos; los intermediarios terminan neutros.

El saldo inicial minimo aritmetico de Morpho bajo esta secuencia es 3305.262344 USDC. Es una necesidad de liquidez del protocolo, NO capital que el propietario de NQC deba aportar, ni un saldo inicial medido. Ademas se necesitan liquidez retirable en el mercado de origen, participaciones del adaptador y condiciones validas en las bovedas. Patrocinar gas no sustituye esos requisitos. La fuente Morpho `src/Morpho.sol`, commit `9cf6d5b844625ba108e36d1cf911f5d2faf7c136`, lineas 200-229, comprueba autorizacion, participaciones y activos suministrados frente a prestados antes del retiro. La identidad del runtime historico no se verifico.

El excedente tras deuda sigue siendo 84.308093 USDC: 60.425142 se convierten a WETH y 23.882951 se transfieren al destinatario externo. Hay aumento de WETH y gas pagado por el emisor; no es beneficio neto de NQC. `Liquidate` se emite antes del repago; `Withdrawal` de WETH no es un Transfer a cero; el campo indexado `to` de `ProfitSwept` contiene USDC, no el destinatario del pago. El evento BuilderPaid no se suma de nuevo a la transferencia nativa.

## Evidencia y ejecucion

La entrada conserva una normalizacion manual reversible de los campos hexadecimales mostrados por el conector, NO una respuesta RPC bruta ni un recibo autenticado. El log Liquidate se contrasta con el log RPC original del archivo aportado. Hashes de eventos y mercados prueban consistencia, no consenso ni estado.

Se ejecutaron 22 pruebas nuevas de estos datos/mutaciones: todas aprobadas. Se reejecutaron aparte 17 pruebas de la entrega anterior: aprobadas; no son nuevas ni estan incluidas en esta suite. No se ejecutaron Solidity, replay original, variante NQC, suites completas de aislamiento/Rust ni CI remoto. No se dispone de checkout completo. El resultado mantiene `live_executable=false`, `nqc_net_profit=null`.

La consulta de calldata fue truncada; raw-trace fallo por 173420 caracteres frente al limite nativo de 100000. Las seis paginas de logs se completaron. Ocho consultas de datos contabilizadas, siete satisfactorias y una limitada por tamano; presupuesto final cero, sin reinicializar sesion. No estan forge/solc/anvil ni NQC_RPC_URL en el entorno local. No se reintento la maquina remota tras su aviso previo de cuota agotada. Cero firmas, bundles, despliegues publicos, fondos o compras.

## Reproducir

Con Python 3.10+ y solo biblioteca estandar, desde esta carpeta:

```
python3 verify.py
python3 src/route_audit.py
```

Salida cero significa consistencia de datos/pruebas, NO elegibilidad de trading. El plan siguiente es obtener calldata/recibo completos, cabeceras y preestado exactos, incluyendo los DOS mercados y las bovedas, y reproducir primero el original. Los eventos no dan un call graph exhaustivo. No completar estado con valores inventados ni modificar reloj o financiar el ejecutor artificialmente para declarar un PASS. Captura competitiva y patrocinio aceptado son verificaciones posteriores separadas.

Este directorio publica codigo, 53 eventos normalizados, log original, pruebas y resultado, no solo un resumen. No integra el analizador en el motor ni certifica el repositorio. Registros detallados, plan de lecturas no ejecutado y reporte extendido se entregan tambien en el ZIP de la conversacion.

Fuentes: ZIP del propietario `NQC_EVIDENCIA_ETHEREUM_90D.zip` (SHA256 7d7b91194d424c63fb61c9233f1a4016ee42dd7cc96faba0fd97b86febba8994); seis paginas Blockscout `/api/v2/transactions/{hash}/logs` consultadas el 21-oct-2026; fuente oficial Morpho fijada arriba; documentacion Geth de prestateTracer (estado tocado, no prueba criptografica). No es NQC079/NQC080 recuperado.
