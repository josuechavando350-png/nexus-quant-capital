# Medición auxiliar de gas

`research/measure_gas.py` vincula observaciones de comisiones a liquidaciones de
un journal completo, verificado por Rust y copiado a Parquet. Funciona offline;
no consulta proveedores, inicia servicios ni modifica la captura original.

```bash
python3 research/measure_gas.py \
  --state evidence/public-capture-v2-20261022/state \
  --evidence evidence/gas-measurement-20261023/blockscout-input.json \
  --output /ruta/nueva/medicion-gas \
  --verifier /ruta/absoluta/nqc-miner
```

El directorio de salida debe ser nuevo. `manifest.json` se escribe al final y
significa que el artefacto está completo, **no que su medición económica lo esté**.
Se conservan respuestas, journal original, owner, configuración, Parquet y hashes
del módulo, verificador y resultados. La salida mantiene la clase del journal:
un fixture sintético no se convierte en evidencia histórica.

## Contrato inicial

- Solo captura independiente completa, histórica o sintética. Se rechazan
  invalidaciones, registros provisionales, scopes incompletos y ventanas de una
  colección sin su contexto de revocación padre. No se admite Shadow retrospectivo.
- Adaptador explícito de Blockscout MCP 0.19.0: respuestas de
  `get_transaction_info` y `get_block_info(include_transactions=true)`, con los
  parámetros públicos exactos. Los tokens de sesión no son entradas del artefacto.
- Se admiten únicamente comisiones de ejecución Ethereum mainnet tipo 2. Otras
  cadenas/tipos quedan desconocidos; no se extrapolan costes de L1 a rollups.
- La respuesta debe corresponder al bloque y segundo UTC del evento verificado.
  Se exige presencia del hash de la transacción en la lista del bloque, además
  de éxito, estado no pendiente y consistencia de límites, precio efectivo,
  comisión total, quema y prioridad. Una lista parcial no prueba ausencia.
- Los enteros monetarios se conservan como cadenas decimales en wei. Se rechazan
  flotantes, booleanos, signos, notación científica, overflow y campos ambiguos.
  No se usan cotizaciones actuales ni `historic_exchange_rate` del explorador.

Para el tipo admitido, `execution_fee = gas_used * effective_gas_price`;
`base_fee_burn = gas_used * base_fee_per_gas`; `priority_fee` es la diferencia.
El precio efectivo se comprueba contra ambos límites EIP-1559. Es contabilidad
de la transacción entera: varios eventos referencian un único registro de coste.
El reparto del coste entre eventos no se inventa.

Fuentes del contrato: [JSON-RPC Ethereum](https://ethereum.org/developers/docs/apis/json-rpc/)
y [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559).

## Límites de confianza y economía

Blockscout es un índice auxiliar. La pertenencia declarada por el índice no es
una prueba Merkle de transacción/recibo, un nuevo quorum RPC ni una certificación
de finalidad. El adaptador no vuelve a verificar los logs del evento en esa fuente.
Los hashes locales prueban conservación y reproducibilidad, no autenticidad
criptográfica del proveedor. Las respuestas completas pueden contener metadatos
ajenos al cálculo; se conservan como datos y no se ejecutan.

`direct_builder_payment_wei`, precio histórico en USD, primer bloque elegible,
bonus y beneficio neto permanecen `null`. Una comisión de prioridad cero no
prueba que no hubo pagos directos al constructor. El agregado solo suma las
transacciones medidas, una vez cada una; si no hay ninguna, también es `null`.
El indicador `all_transaction_fees_measured` es falso para una muestra vacía o
con algún coste desconocido. Los gates económicos y de activación siguen falsos.

La entrada está limitada a 8 MiB y 256 llamadas; el journal a 8 MiB/10.000
registros. No hay seguimiento automático de paginación ni red en este módulo.
La extensión a recibos RPC redundantes, pruebas, rollups, trazas y precios debe
añadir adaptadores con validación propia, no convertir faltantes en ceros.
