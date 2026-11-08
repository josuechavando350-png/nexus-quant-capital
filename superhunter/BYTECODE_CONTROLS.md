# Bytecode nativo ligado a controles CHC propios

Este componente compila las mismas tres fuentes del laboratorio `solidity_stateful`
y conserva su código de creación y su código de ejecución. No contiene una EVM,
no despliega contratos, no acepta objetivos y no genera estrategias de explotación.
La aserción de fuente comprobada por CHC **no** se convierte en una garantía sobre
el comportamiento del bytecode. Se conserva `evm_executed=false`.

## Uso

Desde la raíz del paquete:

```bash
python3 -m superhunter build-stateful-bytecode \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --out /directorio-privado/build-nuevo
python3 -m superhunter replay-stateful-bytecode \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --bundle /directorio-privado/build-nuevo
```

Salida 1 significa `NATIVE_BYTECODE_BUILT_EVM_PENDING`: la generación y sus
comprobaciones concluyeron, pero la aceptación EVM sigue pendiente. Salida 2
significa bloqueo/error; no se produce una aprobación por faltar un motor.
No existe código 0 que aparente una aceptación EVM completa en esta unidad.

## Lo que ejecuta

1. Verifica el SHA-256 del binario recibido frente al pin oficial 0.8.30.
2. Ejecuta el laboratorio CHC con su presupuesto normal: compilador, Z3,
   no-vacuidad y referencias de estados/secuencias, incluidos los controles
   correcto, alterado e inalcanzable ya existentes.
3. Compila esas MISMAS fuentes de propiedad a creación, runtime, ABI, metadata
   y layout con Cancun, optimizador desactivado y model checker desactivado para
   esta fase de generación de código. No se admiten nuevas fuentes por CLI.
4. Comprueba igualdad de fuente y de settings semánticos entre fases. Las únicas
   diferencias admitidas son las salidas solicitadas y la activación del checker.
5. Rechaza símbolos de bibliotecas pendientes, referencias de inmutables fuera
   del perfil, ABI inesperada, código vacío o mal formado y errores del JSON.
6. DIABLO registra los hashes que ligan fuente, prueba y cada objeto compilado.
7. Replay vuelve a generar fuente/consultas y recompila/resuelve todo; nunca
   ejecuta fuentes, consultas o bytecode recibido dentro del paquete.

Por ejecución concluida hay 16 procesos de compilador (13 de la fase CHC y 3 de
bytecode) y seis consultas de solver. No son 16 contratos ni vulnerabilidades.
El receipt conserva las salidas originales. La cuenta corresponde a este flujo
fijo, no a instrumentación de un productor remoto.

## Contrato de confianza

Los hashes y AuditLog vinculan bytes, pero no prueban autoría remota. El replay
usa los mismos solc y Z3. No hay un compilador independiente ni comprobador de
certificados de solver. Una configuración de compilación incompatible queda
rechazada en lugar de transferir una conclusión de fuente a otro build.

La inicialización está en el código de creación. No se fabricaron slots iniciales
para aparentar ejecución del constructor. Ni ese código ni el runtime se ejecutan
por esta unidad. Los artefactos generados son aptos para la siguiente aceptación
local, NO para despliegue o uso financiero.

La fuente incorrecta es un control aritmético propio y conocido. No usa tokens,
cuentas reales, RPC, llamadas a terceros ni movimientos de dinero. Su estado
fallido observado por las referencias es anterior a una posible reversión, no
un saldo confirmado por una EVM.

## Evidencia y continuidad

Base exacta: `SUPERHUNTER_estado_persistente_1467.zip`, carpeta `codigo/`.
Se conservan todos sus tests. La nueva suite utiliza capturas de salidas REALES
del compilador, identificadas como tales; algunos tests sustituyen la ejecución
para comprobar orquestación. Esos mocks no se cuentan como compilación nueva.
La aceptación nativa separada vuelve a usar el ejecutable real, sin mocks.

El componente se registra en CLI/QA y depende de los módulos previos de compilación,
CHC, archivos privados y auditoría DIABLO. El recorrido `review-platform` conserva
sus etapas previas: pasar QA no significa haber ejecutado la aceptación nativa.
Esta se ejecuta con los dos comandos explícitos de arriba y se documenta aparte.

No se cambian catálogos 27/50/25, fuentes nativas, workflows ni sistemas externos.
No se ejecuta la suite histórica completa NQC o su verificador de aislamiento:
el material recuperado es el paquete superhunter, no un checkout íntegro NQC.

Referencias oficiales consultadas:
- https://docs.soliditylang.org/en/v0.8.30/using-the-compiler.html
- https://docs.soliditylang.org/en/v0.8.30/smtchecker.html
- https://geth.ethereum.org/downloads

## Bloqueo externo identificado

No hay motor EVM instalado. Las solicitudes a PyPI/npm fallaron por DNS y el
intento de descargar la distribución oficial Geth & Tools falló. No se implementó
una EVM casera para simular que se cubrió el requisito.

Archivo candidato para la siguiente etapa (Linux amd64):
`geth-alltools-linux-amd64-1.17.10-1df30b18.tar.gz`, procedencia oficial Geth.
Su archivo de firma es el mismo nombre con `.asc`. Antes de ejecutar sus binarios
se debe verificar procedencia/PGP con una clave oficial obtenida separadamente;
un MD5 de transporte por sí solo no autentica el software.
