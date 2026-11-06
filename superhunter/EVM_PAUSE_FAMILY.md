# SUPERHUNTER — perfil EVM de pausa (laboratorio propio)

Este incremento añade una familia diferente de regresión: un contrato propio
`PauseLedger`, con saldos internos `remaining` y `distributed` y estado `paused`.
Las versiones difieren exclusivamente por la línea de guardia
`require(paused == 0)` antes de una distribución. La versión sin guardia es
**una mutación defectuosa intencionalmente creada**, no una vulnerabilidad
original encontrada en un protocolo de un tercero.

## Ruta real

1. Fuentes literales y configuraciones compiladas mediante el ejecutable fijado
   de `solc` 0.8.30; se requiere AST, layout, ABI y objetos de bytecode.
2. Ejecución de constructores reales y cinco secuencias de cuatro operaciones
   con Geth EVM 1.17.10. Dos perfiles de compilación (legacy e IR optimizado)
   por versión de contrato: cuatro constructores y 80 llamadas.
3. Un modelo independiente predice retorno, errores y estado persistente. La
   salida real de Geth se comprueba para **cada** operación, incluidas reversiones
   y agotamientos de gas. Cada secuencia parte de su propio constructor.
4. Un comprobador separado examina, desde el estado observado, si se distribuyeron
   unidades positivas durante una pausa. El estado solo cuenta si la operación
   terminó aplicada; las operaciones revertidas no cuentan como efectos.
5. El replay recompila, ejecuta y compara la evidencia; también se verifica
   la bitácora `AuditLog` original de DIABLO.

Comandos desde la carpeta que contiene `superhunter/`:

```bash
python -m superhunter run-owned-pause-lab \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /ruta/evm \
  --source-digest SHA256_DEL_INVENTARIO_QA_ACTUAL \
  --out /directorio/privado/nuevo

python -m superhunter verify-owned-pause-lab \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /ruta/evm \
  --source-digest SHA256_DEL_INVENTARIO_QA_ACTUAL \
  --bundle /directorio/privado/nuevo
```

La huella es `sha256(canonical(quality.source_snapshot()))` de **ese** código.
No puede reemplazarse por una cadena arbitraria sin bloquear la ejecución.
La consola no expone código, rutas privadas ni contenidos de los expedientes.

## Límites

No hay RPC, balances ERC-20, usuarios reales, datos de terceros ni envíos.
La fuente propia y los cinco escenarios son conocidos antes de ejecutar:
**NO es una prueba ciega**, ni una prueba de que el fuzzing haya descubierto un
error desconocido. La ruta demuestra detección de una propiedad declarada en una
familia de código diferente y un cambio persistente, no certeza de ausencia de
bugs. El replay utiliza los mismos compilador y EVM, no dos implementaciones
independientes, y depende de sus respectivos binarios fijados.

No se agregaron binarios al repositorio ni se modificaron fuentes históricas.
La suite histórica NQC/aislamiento del repositorio completo queda fuera del
alcance del paquete acumulativo local.
