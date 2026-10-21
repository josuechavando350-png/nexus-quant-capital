# Variante NQC — NO EJECUTADA

Estado: `BLOCKED_BY_UNVALIDATED_ORIGINAL`. Beneficio neto: `null`.
No se crearon saldos, no se aplicó `deal`, no se firmó ni transmitió una transacción.
No hay ganador económico medido entre A y B.

| Estrategia | Lo sustentado | Lo pendiente |
|---|---|---|
| A. Callback directo Morpho | La fuente fijada transfiere colateral, llama `onMorphoLiquidate` si data no está vacía y después cobra deuda | Ruta completa de redención, acceso de NQC, liquidez de retiro, gas y patrocinio |
| B. Flash loan / swap | Puede proponer financiación temporal de deuda antes de liquidar | Proveedor y liquidez exactos, fee, orden efectivo de llamadas, gas y resultado sobre el mismo estado |

La fuente Morpho revisada es `morpho-org/morpho-blue` commit
`9cf6d5b844625ba108e36d1cf911f5d2faf7c136`, `src/Morpho.sol`.
Su función `flashLoan` devuelve el principal sin añadir comisión en ese código.
Eso no verifica su identidad histórica desplegada ni convierte en cero el coste total de B.
A evita esa llamada de financiación externa; **no demuestra por sí sola mayor beneficio**.

La conversión obligatoria sigue siendo PT -> Pendle/SY -> stcUSD/cUSD -> reserva -> estrategia ->
bóveda -> adaptador -> retiro del segundo mercado Morpho -> USDC, con sus contratos y autorizaciones reales.
La secuencia económica de los eventos de USDC discurre en dirección inversa desde Morpho hasta el ejecutor.
El repago al mercado liquidado no crea automáticamente liquidez retirable ni participaciones del adaptador
en el mercado de retiro. No se verificaron restricciones de acceso de cada intermediario.

## Restricción de liquidez dependiente del orden

El callback original requiere, como cota aritmética bajo sus eventos, 3305.262344 USDC globales en Morpho
antes del retiro. No es una lectura de saldo ni una condición suficiente.

Para un flash Morpho hipotético de D=3220.954251 USDC:

- Si se liquida con callback vacío y se repaga D **antes** de redimir R=3305.262344, el prefijo global
  sería `−D,+D,−R,+D`; la cota es `max(D,R)=3305.262344`.
- Si se mantiene D prestado y se redime R **antes** del repago de la liquidación, la cota asciende
  a `D+R=6526.216595` USDC. No atribuir esta cota al primer orden de llamadas.

Ambas son aritmética condicional, no forks ni estrategias ejecutadas. El primer orden podría cambiar
los estados observados por intermediarios respecto al original; necesita reproducción real.

Para afirmar cero capital propietario deben empezar a cero tanto el ejecutor como la EOA y los
beneficiarios pertinentes, sin fondos preexistentes financiando creación, aprobaciones o ejecución.
El anticipo externo debe acreditarse antes de los controles de solvencia de gas, con reembolso y costes
contabilizados. Un `prank` o una llamada interna sin receipt no prueba financiación de una EOA vacía.
Los resultados A/B, sus receipts, despliegue, gas, fees y beneficio mínimo permanecen pendientes.
