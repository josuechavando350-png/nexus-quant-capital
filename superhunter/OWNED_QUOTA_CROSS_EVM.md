# Cuotas propias en dos implementaciones EVM

El corpus cerrado de #60 se ejecuta en Geth 1.17.10 y EELS 2.20.0 sobre Cancun:
seis variantes de fuente, dos correctas y cuatro con defectos sembrados. Cada
motor recompila dos formas por variante y ejecuta 12 constructores y 228 llamadas.
Las decisiones siguen agrupadas en seis casos; ambas ejecuciones están correlacionadas.

Se cotejan hashes de compilación/bytecode, estado inicial, estado persistido,
resultado (commit/revert/gas agotado) y retorno de cada llamada. EELS decodifica
los tres campos uint16 mediante segmentos de bytes; Geth usa máscaras de bits.
El detector recibe las observaciones, no la etiqueta del caso. La evaluación
conserva falsos positivos, omisiones y las ablaciones de estado/resultado de #60.

Las 23 dependencias de EELS conservan sus versiones y hashes de #59, en un entorno
separado del QA: cryptography 45.0.7 para EELS y 46.0.4 para QA. No se relajan pins.
Cada worker mantiene 180 s pared, 90 s CPU, 2 GiB y 20 MiB por archivo; los workers
Python arrancan con prefijo de caché nuevo. Geth usa el descriptor sellado de #60.

```sh
python -m superhunter compare-owned-quota-engines --solc SOLC --evm GETH --source-digest DIGEST --out PAQUETE_NUEVO
python -m superhunter verify-owned-quota-engines --solc SOLC --evm GETH --source-digest DIGEST --bundle PAQUETE
```

El verificador vuelve a compilar y ejecutar ambos motores en procesos nuevos y
exige identidad exacta de los artefactos regenerados. Un hash coherente por sí solo
no establece concordancia con una nueva ejecución. Los tests unitarios usan datos
sintéticos explícitos; la aceptación nativa se registra por separado.

Se comparten compilador, fuentes, entradas, host y detector. No se comparan costes
de gas ni raíces de cuentas; no se certifica toda la EVM ni productores independientes.
No es evaluación ciega, hallazgo externo ni evidencia de generalización. No admite
fuente, transacción, calldata, RPC o contrato arbitrarios; solo los seis casos propios.
