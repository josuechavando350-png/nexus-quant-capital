# Ethereum + Base: alcance autorizado y primer acceso

Decisión explícita del usuario del 9 de octubre de 2026, Ciudad de México:
trabajar Ethereum y Base. Ethereum conserva su Census e insumos; Base pasa de
propuesta a investigación activa, con población y evidencia propias. Las demás
redes permanecen en espera. Esto no declara terminado ninguno de los censos.

## Estado real de Base

El 10 de octubre a las **05:19:56 UTC**, el servidor original hizo una única
consulta `eth_chainId` a `https://mainnet.base.org`. Recibió HTTP **403**, cuerpo
exacto `error code: 1010`. El colector se detuvo sin reintentos ni otro endpoint.
`capture-001.zip` conserva request, response, headers, tiempos actuales, progreso,
terminal fallido y fuente exacta. SHA-256:
`8aae30b9c374603b3461ab46d5cf9644d4d45ebfdf4f4539bc621622d7de9819`.

No se obtuvo chain ID, bloque, reserva, balance ni precio de Base. El número de
reservas y beneficio son desconocidos, no cero. La denegación corresponde a ese
endpoint desde ese servidor; no prueba que toda Base o todo DigitalOcean estén
bloqueados. Hace falta acceso RPC de Base autorizado que acepte consultas desde
el servidor. No se recuperan credenciales ni se contrata servicio por esta tarea.

## Colector preparado, todavía sin validación on-chain

`collect.py` sólo permite seis métodos de lectura, un trabajador, intervalo
mínimo 1.1 s, máximo 1,200 solicitudes y salidas nuevas. No tiene reintentos ni
failover. Conserva errores HTTP/RPC y rechaza respuestas ambiguas. Sus pruebas
sintéticas verifican controles del código; no sustituyen una captura real.

El plan busca el bloque Base inmediatamente anterior o igual al timestamp del
ancla Ethereum, **2026-10-01T05:23:35Z**. Busca el límite por timestamp sin
equiparar alturas de redes; comprueba el bloque siguiente y el padre. Todas las
consultas de estado usan blockHash y requireCanonical. Compara el header del
ancla antes/después. El hash observado no implica prueba Merkle o nodo independiente.

Para el primer despliegue Aave, lee proveedor, pool, oracle y data-provider del
estado fijado; conserva bytecode, implementación EIP-1967, lista de reservas,
configuración cruda, índices, decimales, precio, balance subyacente del aToken y
supplies aToken/deuda variable. Los balances son observaciones de inventario;
no prueban capital flash utilizable, compatibilidad ni beneficio de Nexus.

El puntero documental proviene de `aave-dao/aave-address-book`, commit
`6a83d11893d6687bf6b9fd091a2a5320b3e1966e`, `src/AaveV3Base.sol`:
[fuente fijada](https://github.com/aave-dao/aave-address-book/blob/6a83d11893d6687bf6b9fd091a2a5320b3e1966e/src/AaveV3Base.sol).
Sus bytes están en `AaveV3Base.source.sol`. No se equipara el contenido documental
actual con configuración histórica; los getters al bloque deberán confirmarla.

## Dependencias siguientes

1. Resolver el acceso Base y validar la captura real con un consumidor offline;
   una captura COMPLETE tampoco será admisión económica.
2. Conciliar descubrimiento Aave por registros/eventos y lista al bloque,
   incluyendo mercados retirados, proxies y cambios. La lista actual de un pool
   no prueba exhaustividad histórica ni de toda Base.
3. Incorporar Morpho Blue mediante despliegue, mercados creados y parámetros
   autenticados; cada población tendrá un ledger separado. No hay mercados
   Morpho Base verificados en este incremento.
4. Reconstruir posiciones y elegibilidad, capital por activo/bloque, callbacks,
   repayment, obligaciones, rutas y compatibilidad. Principal y salida deben
   resolverse dentro de la misma cadena; un puente no financia un préstamo flash
   entre Ethereum y Base.
5. Medir costes completos, competencia, captura, conflictos y capacidad por
   cadena/estrategia antes de agregarlos. TVL, número de pools o rapidez no son P&L.

## Costes y capital compartido

La política `../capital-policy.json` no se duplica: **MXN 2,000 acumulados** de
aportación sólo para gas entre ambas redes y todas las wallets. Las claves de
cuenta/nonce incluyen chain_id; el gas Budget existente ya aplica ese ámbito.
No existe permiso nuevo para firma, gasto, principal, colateral o reinversión.

Ethereum y Base necesitan adaptadores de coste distintos. Para Base no basta
gasUsed por effectiveGasPrice: debe incorporarse el coste L1 y cualquier cargo
adicional aplicable al régimen del bloque, acreditando cuándo vale cero. No se
importa un precio actual a un bloque histórico ni se duplica la priority fee ya
incluida. En preejecución se reserva un límite conservador; los costes desconocidos
siguen null. Fuentes oficiales consultadas el 10 de octubre de 2026:

- [Identidad y RPC](https://docs.base.org/base-chain/api-reference/ethereum-json-rpc-api/eth_chainId).
- [Costes Base](https://docs.base.org/specifications/transactions/network-fees).
- [Orden de transacciones](https://docs.base.org/specifications/transactions/transaction-ordering).

La documentación de Flashblocks describe prioridad y llegada: el orden ya fijado
no se revierte por una puja posterior. Esto define qué medir, sin demostrar
ventaja exclusiva ni captura. No se inicia flujo de transacciones en este trabajo.

## Reproducción offline de la denegación

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/base_expansion/readback.py --out /tmp/base-readback-new.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s migration/census_v2/base_expansion -p 'test_base.py' -v
```

El readback sólo puede autenticar el fallo observado; no certifica un futuro
colector, un proveedor, la solvencia de activos o Census. La autoridad independiente
Market/Capital/Economic Truth sigue pendiente para cada productor y alcance.
