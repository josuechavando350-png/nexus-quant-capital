# Ejecutor nativo de Solidity — estado y contrato operativo

## Estado de esta entrega

Código ejecutor implementado; **compilación solc y replay de una compilación NO
realizados en esta sesión**. El binario no estaba instalado. npm/descarga directa
no estaban disponibles y el dispositivo de desarrollo conectado estaba offline.
No se incluye un compilador simulado ni se promocionan los fixtures de JSON a
resultados producidos por solc. Las pruebas de este módulo NO cierran el hito de
integración con Solidity/EVM.

El ejecutor acepta únicamente el binario oficial Linux-amd64:

- Versión: `0.8.30+commit.73712a01`.
- SHA-256: `f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7`.
- Índice consultado: https://binaries.soliditylang.org/linux-amd64/list.json
- Archivo: https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v0.8.30+commit.73712a01

Se fija esta versión para corresponder a los perfiles de almacenamiento existentes;
no se afirma que sea la más reciente ni la recomendada para desplegar. No se
redistribuye el binario ni se instala software automáticamente.

## Integración implementada

CLI → validación de input → comprobación de checksum → bytes sellados en memoria
→ worker con límites → solc Standard JSON sin callback → clasificación de errores
→ artefactos y auditoría DIABLO. `replay-compilation` exige el hash de entrada
custodiado fuera del paquete y vuelve a ejecutar el MISMO compilador. No es
verificación por un compilador independiente.

Las salidas input.json/output.json son consumibles por `review-compiler-layout`,
suministrando su manifiesto externo habitual. Esa revisión adicional no se ejecuta
implícitamente: compilar y comprobar compatibilidad del layout son pasos distintos.
La compatibilidad end-to-end con salidas REALES de solc sigue pendiente de prueba.

## Uso cuando el binario esté disponible localmente

Desde la raíz del código, en Linux x86_64, sin RPC ni claves:

```bash
python3 -m superhunter inspect-solc --binary /ruta/privada/solc-0.8.30
```

Crear una entrada para un contrato propio inocuo:

```python
from pathlib import Path
from superhunter.native_compile import standard_input
source = "// SPDX-License-Identifier: MIT\npragma solidity 0.8.30;\ncontract C { uint128 public value; }\n"
Path("/tmp/sh-solc-input.json").write_bytes(standard_input({"C.sol": source}))
```

```bash
python3 -m superhunter compile-solidity --binary /ruta/privada/solc-0.8.30 \
  --input /tmp/sh-solc-input.json --out /tmp/sh-solc-output-nuevo
sha256sum /tmp/sh-solc-input.json
python3 -m superhunter replay-compilation --binary /ruta/privada/solc-0.8.30 \
  --bundle /tmp/sh-solc-output-nuevo --expected-input-sha256 HASH_EXTERNO_REAL
```

`HASH_EXTERNO_REAL` es la referencia obtenida por quien verifica; no copiar sin
revisión el hash declarado por un paquete desconocido. La salida debe estar fuera
del checkout y no existir. Los originales contienen código/diagnósticos privados.

Exit 0: operación concreta completada (inspect-solc no es compilación).
Exit 1: solc devolvió errores de compilación, también si el proceso salió 0.
Exit 2: rechazo/error. No afirma que el proceso jamás haya arrancado.
Exit 3: compilador/plataforma no disponible; no hay compilación ni carpeta válida.

## Límites de ejecución y de confianza

Solo inline sources, 16 archivos, 64 KB de fuente; settings fijados. No URL sources,
remappings, flags libres, callbacks de importación, optimización ni model checker.
Se solicitan AST y storageLayout; no bytecode para despliegue. El compilador usa
`--standard-json --no-import-callback`. No se ejecutan instrucciones del contrato.

Antes de ejecutar, se leen y hashean los bytes completos; se copia la imagen
verificada a un memfd sellado. La ejecución usa ese descriptor, no vuelve a abrir
la ruta original. El child recibe entorno mínimo sin variables/secretos heredados.
Límites por proceso: 15 s CPU, 30 s de pared, 1 GiB de direcciones, menos de 2 MB
por salida; sin core dumps. No es un sandbox de kernel, no impide vulnerabilidades
del propio compilador y no promete aislamiento de código nativo hostil.

El checksum se fijó desde el índice público oficial. Es una raíz de confianza,
no una compilación reproducible auditada del propio compilador. Los recibos son
atestaciones locales, no firmas externas. La comprobación interna del paquete no
prueba ejecución. Solo el replay explícito ejecuta y contrasta de nuevo; un
resultado repetible no demuestra ausencia de vulnerabilidades.

## Lo probado aquí y lo no probado

Los tests comprueban esquemas, checksum incorrecto/ausente, no sobrescritura,
protección de rutas, diagnósticos privados, referencia externa, artefactos alterados,
la diferencia entre errores JSON y éxito de proceso, y el límite de proceso del
SO usando el intérprete Python REAL. Ese test NO usa Python para fingir ser solc:
la validación de versión y la API pública lo rechazan como compilador.

Los fixtures JSON se etiquetan en el archivo de tests. No hubo invocación de solc,
compilación correcta, compilación errónea real, replay de compilador, Slither, Forge,
EVM, objetivos externos, CI de GitHub ni benchmark de vulnerabilidades.

La primera ejecución nativa con el binario oficial debe probar, como mínimo:
contrato válido, error de sintaxis con proceso 0, import ausente con callback
inhabilitado, igualdad exacta en replay, y consumo del AST/layout real por v4.
**Estos son criterios de aceptación pendientes, no pruebas ya aprobadas.**

Referencias oficiales consultadas en esta entrega:
https://docs.soliditylang.org/en/v0.8.30/using-the-compiler.html
https://docs.soliditylang.org/en/v0.8.30/path-resolution.html
https://docs.soliditylang.org/en/v0.8.30/installing-solidity.html
