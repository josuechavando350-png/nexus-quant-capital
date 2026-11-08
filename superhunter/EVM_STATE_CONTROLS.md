# EVM local: constructor, persistencia y reversión

Esta ruta ejecuta el binario oficial `evm` de Geth 1.17.10 sobre los tres
controles aritméticos propios ya definidos en `solidity_stateful.py`. No acepta
fuentes, contratos, calldata, RPC, direcciones o estados externos por CLI.
No descubre vulnerabilidades ni se conecta a una blockchain.

## Recorrido conectado

`solidity_stateful` genera las consultas CHC desde las fuentes fijas con solc
0.8.30 y las resuelve con Z3. `bytecode_controls` vuelve a compilar exactamente
esas fuentes para producir creación/runtime/ABI/layout. `evm_execution` ejecuta
el constructor en un estado vacío y utiliza exclusivamente el estado observado
para las llamadas siguientes. No precarga las variables de Solidity ni reemplaza
el runtime entre llamadas. La bitácora original de DIABLO liga los resultados.

El comando de aceptación nativa es separado de `review-platform`, para que la
suite de tests de parser/orquestación nunca se presente como ejecución EVM:

```bash
python3 -m superhunter run-evm-state-controls \
  --solc /ruta/al/solc-oficial --evm /ruta/al/evm-verificado \
  --out /ruta/privada/caso-nuevo
python3 -m superhunter replay-evm-state-controls \
  --solc /ruta/al/solc-oficial --evm /ruta/al/evm-verificado \
  --bundle /ruta/privada/caso-nuevo
```

Cada ejecución/replay recompila, resuelve y realiza 3 creaciones y 18 llamadas
nativas. Los controles se regeneran desde el código propio; nunca se ejecutan
fuentes, consultas, órdenes ni estados contenidos en un paquete recibido. La
reproducción exige la misma salida determinista y usa los mismos motores; no es
una verificación por dos EVM independientes ni un certificado formal de bytecode.

## Condiciones comprobadas

El estado inicial real del constructor es debit=15, credit=0, steps=0. Se aplican
seis llamadas conocidas por control: cantidades 2, 16, 3, 4 y 0 con presupuesto
normal, y otra llamada con gas=1. La cantidad 16 es deliberadamente inválida.

- Conservación correcta: 3 llamadas aplicadas, 2 reversiones de precondición,
  1 agotamiento de gas. Estado final (6, 9, 3).
- Unidad adicional en el tercer paso: 2 llamadas aplicadas, 1 reversión de
  precondición, 2 reversiones Panic(0x01), 1 agotamiento de gas. Estado final
  (10, 5, 2); las escrituras tentativas no permanecen.
- Precondición imposible: 5 reversiones y 1 agotamiento de gas. Estado inicial
  preservado; no se declara una propiedad universalmente segura por no ejecutarse.

Se comprueba el contenido persistente completo de ambas cuentas tras cada
reversión, además de decodificar los campos usando el layout recién compilado.
Se distinguen retorno normal, `execution reverted` con datos Panic(0x01),
reversión vacía y `out of gas`. Un proceso con exit=0 no se confunde con una
llamada Solidity exitosa: el runner de Geth comunica esos errores en su salida.

Geth `evm run` usa genesis.gasLimit por delante del argumento --gas si el primero
no es cero. El módulo exige que AMBOS sean el presupuesto esperado. Sin esa
igualdad, una prueba de gas=1 podría ejecutarse realmente con millones de gas.

## Herramientas y confianza

Archivo recibido: geth-alltools-linux-amd64-1.17.10-1df30b18.tar.gz.
SHA-256 de archivo:
`f991c32e5b7bb68db97a1b06d50c7c06f6aa9ae84d8f6f9b2301dc02cad2a7cf`.
La firma OpenPGP adjunta se verificó con la clave cuyo fingerprint completo
coincide con el publicado en la página oficial de Geth:
`FDE5A1A044FA13D2F7ADA019A61A13569BA28146`.
La copia de la clave pública se obtuvo de un archivo público histórico; su
fingerprint se corroboró por separado con la página oficial. No se afirma
confianza de una red PGP ni se deduce autenticidad solo del nombre del archivo.

Solo se extrajo el miembro regular evm: 42,001,080 bytes, SHA-256
`d8cfddad15a8c601e7b069bc5973ad073dbc2d632b8c5ab50e513ef27c53d6da`.
El ejecutor comprueba tamaño, hash, formato ELF y plataforma antes de compilar,
y ejecuta una copia de bytes sellada mediante memfd. No incluye los binarios
en la entrega ni modifica los archivos que aportó el usuario.

El worker limita CPU, memoria, tamaño de salida y tiempo real. El ambiente no
hereda claves ni endpoints RPC. Es un proceso de herramientas propias fijadas,
NO un sandbox de sistema operativo para código hostil. No inicia geth como nodo.
La ausencia de opciones de red no equivale a un cortafuegos del sistema.

## Qué NO se demuestra

Estos son message calls locales en memoria, no transacciones firmadas o minadas.
No hay tokens, precio, gas pagado, mempool, fondos, recompensas ni objetivo externo.
Una violación observada antes de `assert` no se trata como dinero robado: el
bytecode revierte la operación. Las propiedades del modelo fuente no se
transfieren automáticamente como teoremas sobre todo el bytecode.

La aceptación reconstruye resultados con las mismas herramientas. Un paquete
internamente coherente puede ser fabricado; la ruta replay lo contrasta ejecutando
de nuevo. Esto no autentica una ejecución histórica remota ni demuestra ausencia
de vulnerabilidades. Los originales de evidencia contienen código y deben
mantenerse privados. Los contadores de tests corresponden al registro de esta
entrega, no a capacidades certificadas de los catálogos 27/50/25.

Referencias primarias consultadas:
- https://geth.ethereum.org/downloads
- https://github.com/ethereum/go-ethereum/blob/v1.17.10/cmd/evm/runner.go
- https://docs.soliditylang.org/en/v0.8.30/control-structures.html
