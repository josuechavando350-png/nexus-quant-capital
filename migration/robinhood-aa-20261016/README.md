# Robinhood: identidad de EntryPoint, caducidad L2 y contabilidad local

Trabajo de investigación NQC del 2026-10-16. **La integración local avanzó;
la monetización todavía no está demostrada.** No autoriza LIVE ni recertifica PFT.
No modifica los 377 blobs archivados de V2 ni las fuentes históricas de Census.

## Resultados

| Puerta | Resultado | Alcance preciso |
|---|---|---|
| EntryPoint v0.7 desplegado | PASS histórico | Los 16.035 bytes recompilados coinciden, incluidos metadatos, con `eth_getCode` archivado en Robinhood, bloque 89.626.392. |
| Caducidad de la variante | PASS local | Usa `ArbSys(100).arbBlockNumber()`, exige chain 4663 y falla si el reloj falta, revierte, devuelve longitud incorrecta o cero. |
| Firma y repetición | PASS local | Cambiar la caducidad invalida la firma; se rechaza repetir el nonce. La firma de la fixture es EIP-191, no EIP-712. |
| Morpho + callback + swap + cobro | PASS sintético | Bytecode oficial de Morpho y EntryPoint, tokens/oráculo/DEX/cuenta/paymaster de laboratorio. |
| Gas y fallos | PASS local | Siete recibos Anvil completos; conciliación depósito → evento → beneficiario y comisión externa del bundler. |
| Presupuesto de patrocinio | PASS de fixture | Reserva conservadora por prefund; no se duplica presupuesto entre operaciones. No existe financiación comercial acreditada. |
| Coste real Robinhood y monetización | BLOCKED | Falta replay de ruta real, coste Nitro/DA, admisión del bundler, fondos externos y P&L prospectivo. |

### Identidad de código

Dirección: `0x0000000071727de22e5e9d8baf0edac6f37da032`.
SHA-256 del runtime: `674d73ee2acf6d72a5b32b6e05150b9ddcfcee0429a0e7914929faccbc2bf4d5`.
Bloque: `89626392`; hash:
`0x2a1e456b73f9477e2a118aa33a46d500d0235c8f0f7b5e7302856b22013d00f7`.

Se reconstruyeron los 18 archivos de dependencias con Solidity 0.8.23,
optimizador 1.000.000, viaIR, Paris y metadatos IPFS. Los dos campos inmutables
de SenderCreator se rellenaron exclusivamente en las posiciones declaradas por
el compilador, usando su dirección derivada de CREATE nonce 1. Después se comparó
**todo** el runtime, sin borrar ni ignorar metadatos. La dirección derivada coincide
también con la publicada por Robinhood.

El archivo principal obtenido del explorador es idéntico al commit oficial. El
explorador informa verificación completa, sin proxy, y esos mismos ajustes. La
lectura directa nueva del RPC público devolvió HTTP 403 en este entorno: esta
identidad prueba la observación histórica, no una lectura RPC fresca de hoy ni
la disponibilidad de un bundler. El endpoint de metadatos completo excedió el
límite del conector y la descarga REST devolvió 403; no se presentan esas lecturas
fallidas como una segunda comprobación del runtime.

Procedencia del RPC: repositorio original `josuechavando350-png/nexus-engine`, run
`38825362707`, artefacto `12015141307`, commit
`b4ad2455a6ad4a0ece154dc675c797b6f37374f5`. ZIP SHA-256:
`5061d602f26b0794634676f9cf20e5aaf6c950018a3747906a57af64d1915404`.
Se conservaron sus tres archivos originales en `evidence/historical-rpc/`.
No se escribió nada en el repositorio original.

### Corrección L2

`prepare.py` valida los blobs fuente y aplica un overlay sólo en un directorio
nuevo fuera del repo. Produce `NqcMorphoRobinhoodL2Lab`, conserva los controles
atómicos anteriores y añade la caducidad al compromiso del callback.
No hay fallback a `block.number`: en Arbitrum ese valor corresponde a un ancestro
no Arbitrum, no al contador L2 recibido por RPC.

La ventana máxima de 16 bloques es una política de laboratorio, no un número
comercial calibrado ni una garantía de segundos/frescura. La igualdad en el bloque
límite se acepta; el siguiente bloque se rechaza. Todavía no vincula la decisión
a un hash de estado ni resuelve reorgs, cambios de precio o inclusión del secuenciador.

### Coste del ciclo completo local

Precio efectivo fijado en **2 gwei**, dinero generado localmente, cuenta ya
desplegada, una UserOperation por bundle, `preVerificationGas=120000` sintético.
Los números de gas de una función `forge test` incluyen el harness y no se usaron
como coste de la transacción comercial.

| Escenario | Gas del recibo | Gas facturado por EntryPoint | Débito patrocinador, ETH ficticio |
|---|---:|---:|---:|
| Éxito, callGas 1.800.000 | 455.745 | 734.345 | 0,001468690 |
| Éxito, callGas 600.000 | 455.745 | 614.345 | 0,001228690 |
| Caducidad L2 | 227.095 | 319.021 | 0,000638042 |
| DEX sin inventario de salida | 490.058 | 555.688 | 0,001111376 |
| Fallo de postOp | 516.874 | 582.491 | 0,001164982 |
| Agotamiento de callGas | 244.271 | 277.479 | 0,000554958 |
| Firma inválida: revierte bundle | 64.046 | No hay evento de operación | 0 |

Reducir el límite de llamada ahorró **0,00024 ETH ficticio / 16,3411 %** al
patrocinador en este ejemplo, sin cambiar el gas real del recibo. EntryPoint v0.7
penaliza con 10 % el gas de ejecución reservado sin usar. No se afirma que 600.000
sea un límite seguro para una ruta real. El bundler pagó 0,000128092 ETH ficticio
en el bundle de firma inválida, aunque el patrocinador no fue debitado.

En el éxito con límite reducido, `postOp` recibe un coste de 0,001062312 ETH,
pero el débito final es 0,001228690 ETH. Liberar presupuesto basándose sólo en
ese argumento infravaloraría el gasto. El excedente de 106,249999 unidades del
token simulado proviene de un DEX con precio fijo y liquidez creada por el test:
**no es ingreso USDG/USD, una oportunidad real ni beneficio NQC**.

El runtime de EntryPoint es el observado en Robinhood, pero Anvil no implementa
Nitro ni sus costes de publicación L1. ArbSys también es una fixture local. Los
recibos excluyen el despliegue inicial de la cuenta, stake, operación del servicio,
pricing de proveedor y la ruta/token/oráculo reales. No extrapolar estos ETH
ficticios al precio de gas o al coste actual de Robinhood.

## Reproducción

Dependencias limpias con estos commits, en subdirectorios del mismo nombre:

- `account-abstraction`: `7af70c8993a6f42973f520ae0752386a5032abe7`
- `openzeppelin-contracts`: `dbb6104ce834628e473d2173bbc9d47f81a9eec3`
- `morpho-blue`: `8e26ca6a8dbc5089edcd67fb576248810fd2870a`

`toolchain.json` fija Foundry 1.7.1 y los SHA-256 de sus binarios y de solc 0.8.19
y 0.8.23. Los tres binarios se compararon con el tar oficial fijado por digest.
Los compiladores proceden de `ethereum/solc-bin`, con hash comprobado contra su
lista oficial. Tras obtener esas dependencias, esta reproducción es offline:

```bash
python migration/robinhood-aa-20261016/reproduce.py \
  --dependencies /ruta/dependencias \
  --foundry-bin /ruta/foundry-bin \
  --solc-019 /ruta/solc-0.8.19 \
  --solc-023 /ruta/solc-0.8.23 \
  --build /tmp/nqc-aa-build-nuevo
```

El destino debe ser nuevo y estar fuera del repo. El runner inicia y termina su
propio Anvil en loopback; no admite URL remota ni fork. Usa exclusivamente una
clave de prueba pública, no credenciales reales. Los logs y recibos quedan en
`results/` del directorio de construcción.

Comprobación de la evidencia guardada:

```bash
python migration/robinhood-aa-20261016/summarize.py
python migration/verify_isolation.py
python -m unittest discover -s migration -p test_isolation.py -v
python migration/engine-v2-20261015/verify_import.py
```

Validación: 13 tests originales de Morpho + 7 originales AA + 19 nuevos =
**39 tests Solidity**, siete escenarios con recibos y nueve tests de aislamiento.
No se modificó Rust; no se volvió a ejecutar toda la certificación PFT/Rust ni
todo el histórico Census. La fixture de cuenta conserva un warning de mutabilidad.
El harness de tests supera EIP-170 por incluir constructores de fixtures y usa
un límite local ampliado; los runtimes individuales comprobados sí caben:
ejecutor 5.482 bytes, paymaster 4.236, cuenta 1.956, escenario 2.769.

Durante el desarrollo se corrigieron una lectura del formato de salida de `cast`,
el límite del harness y la espera del recibo local. El primer intento de cliente
Anvil separado no compartía espacio de red; `run_local.py` resuelve esto creando
cliente y nodo juntos. Los resultados finales corresponden al runner corregido.

## Siguiente decisión

[SPONSORSHIP.md](SPONSORSHIP.md) explica la política financiable propuesta y los
proveedores investigados. La siguiente puerta requiere un endpoint de lectura
utilizable, mercado y ruta concretos, estado fijado, costes Nitro/DA y cuenta
realista. Después: admisión del bundler, financiación externa acreditada sin
recurso personal y registro prospectivo de todos los intentos. No se ha abierto
ninguna obligación de pago ni se ha autorizado LIVE.

Fuentes de protocolo:

- [Robinhood: AA y contratos desplegados](https://docs.robinhood.com/chain/account-abstraction/)
- [Robinhood: gas y tarifas](https://docs.robinhood.com/chain/gas-and-fees/)
- [Arbitrum: números de bloque](https://docs.arbitrum.io/arbitrum-essentials/arbitrum-vs-ethereum/block-numbers-and-time)
- [Arbitrum: estimación de gas](https://docs.arbitrum.io/arbitrum-essentials/how-to-estimate-gas)
- [EntryPoint v0.7 oficial](https://github.com/eth-infinitism/account-abstraction/tree/7af70c8993a6f42973f520ae0752386a5032abe7)
