# Estados históricos Aave: salud y precios

`read-aave-state` reconstruye de 1 a 64 cierres de bloque consecutivos anteriores
a un evento Aave V3. En cada bloque consulta la salud de una cuenta, resuelve el
proveedor de direcciones y el oráculo vigente, y conserva los precios de hasta
cuatro activos junto con su moneda base y unidad. Los enteros de 256 bits se
publican como cadenas decimales, sin redondear mediante coma flotante.

Las lecturas usan `eth_call` con `blockHash` y `requireCanonical: true`
([EIP-1898](https://eips.ethereum.org/EIPS/eip-1898)). Todos los proveedores
configurados deben coincidir en los bytes. Se verifican cadena, finalización,
hash esperado del evento, continuidad de padres y timestamps, y se vuelven a
comprobar todos los bloques muestreados y los anclajes. Una falta de archivo,
respuesta incompleta, desacuerdo o cambio de bloque produce error; no hay
sustitución por `latest` ni por otro número de bloque.

La superficie RPC admite exclusivamente seis getters de lectura: el proveedor
de direcciones del pool, su oráculo, moneda base, unidad, datos de la cuenta y
precio de un activo. Emisor cero, valor cero y límite de gas fijo; no admite
overrides de estado ni parámetros adicionales. Una consulta no firma ni envía
una transacción y no consume el presupuesto operativo de gas.

## Preparación y ejecución

```bash
python3 research/prepare_aave_reads.py \
  --state /ruta/journal-completo \
  --output /ruta/nueva/planes \
  --verifier /ruta/absoluta/nqc-miner --lookback 16
```

El preparador verifica el journal con el ejecutable Rust real, conserva una
copia exacta y un export Polars, y produce como máximo 32 planes. Cada plan queda
ligado al evento, prestatario, activos, secuencia y hash de la línea original.
Exige todos los scopes completos y sin revocación. Rechaza Shadow y ventanas de
colección desprendidas de su contexto padre. Una muestra sintética nunca se
reclasifica como histórica y no se admite en el comando RPC en vivo.

La plantilla generada debe vincularse a `about` mediante
`scripts/bind_run_config.py`. Las variables RPC son las propias del scope
`NQC_MINER_RPC_…`; no se serializan sus valores. Con la configuración v2 ligada
al binario limpio:

```bash
nqc-miner validate-aave-plan --config /ruta/config.json --plan /ruta/plan-000.json
nqc-miner read-aave-state --config /ruta/config.json --plan /ruta/plan-000.json
```

El primer comando no usa red. El segundo publica JSON en stdout; corresponde al
capturador conservarlo junto con configuración, plan, identidad del ejecutable y
errores. El capturador específico de la evidencia de este bloque y su auditor
están en `evidence/aave-state-public-attempt-20261023/`. No constituyen un servicio
continuo ni un importador productivo de estados.

## Interpretación

Un factor de salud menor que uno con deuda marca un episodio observado. Se
recorre cada bloque: la salud puede empeorar, recuperarse y volver a empeorar.
Los episodios indican si sus límites quedan fuera del intervalo observado.

**Salud baja no demuestra elegibilidad ejecutable.** La versión desplegada,
reservas activas/pausadas, uso de colateral, deuda concreta, sentinel y otras
reglas del protocolo requieren comprobaciones adicionales. El cierre de B−1
tampoco reconstruye el estado inmediatamente anterior a una transacción en B.
Por eso `first_eligible_block` y `liquidation_delay_blocks` permanecen `null`.

Los precios son valores devueltos por el oráculo del protocolo en ese bloque,
con sus unidades originales. No prueban frescura, liquidez ejecutable, ingreso
realizado ni rentabilidad. Una dirección base cero se identifica como USD
según la interfaz, sin convertirla en certificación del contrato desplegado.
Cada muestra conserva su propia configuración; se señala cualquier cambio.

El acuerdo entre proveedores no prueba independencia de operadores ni
autenticidad criptográfica del estado. El informe Rust no recibe el journal:
`source_journal_binding_verified` queda falso. La auditoría separada de esta
captura verifica ese vínculo mediante la preparación reproducida y conserva
su resultado sin modificar el informe original.

## Interfaces revisadas

Se revisaron las interfaces públicas de `aave/aave-v3-core`. Los blobs de origen
quedan identificados para distinguir la revisión ABI de una certificación de
implementación o proxy en la cadena:

| Interfaz | Blob Git revisado |
| --- | --- |
| [IPool.sol](https://github.com/aave/aave-v3-core/blob/master/contracts/interfaces/IPool.sol) | `ef306e737f93a6ae9a4e54fb2ed3684aee35b64f` |
| [IPriceOracleGetter.sol](https://github.com/aave/aave-v3-core/blob/master/contracts/interfaces/IPriceOracleGetter.sol) | `0e0df3e73c40ad58ddc99d742f67e3e1b7a85bef` |
| [IPoolAddressesProvider.sol](https://github.com/aave/aave-v3-core/blob/master/contracts/interfaces/IPoolAddressesProvider.sol) | `587a0d0bc9563688e301cb782144b935d57a5b68` |

La revisión de `ValidationLogic.sol`, blob
`75218f0549067bf1a1a037d401668abe3fcba648`, confirma por qué el criterio de salud
por sí solo no representa todas las condiciones de liquidación. Estos enlaces
de rama pueden cambiar; los identificadores de blob registran lo revisado.

Resultados y limitaciones de la ejecución real:
[AUDIT_AAVE_STATE_20261023.md](AUDIT_AAVE_STATE_20261023.md).
