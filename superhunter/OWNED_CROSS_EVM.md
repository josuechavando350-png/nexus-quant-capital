# Dos implementaciones EVM sobre controles propios

Este perfil ejecuta los cuatro contratos sintéticos ya existentes de pausa y
autorización con Geth y py-evm. Cada variante se compila con solc 0.8.30, una vez
con generación legacy y otra con IR optimizado: ocho constructores y 144 llamadas
por motor. El segundo motor ejecuta el bytecode; no llama al modelo de referencia
ni copia las observaciones de Geth.

La comparación exige igualdad de los bytes de compilación, almacenamiento del
constructor, estado antes y después de cada llamada, éxito/reversión/gas agotado
y retorno. Cada escenario empieza desde el constructor y cada llamada conserva
el estado persistido con un contexto EVM nuevo. `apply_message` aporta la
restauración del estado cuando la ejecución falla. No se usa `execute_bytecode`
como sustituto de esa frontera de llamada.

## Ejecución reproducible

En un entorno Linux x86_64 con CPython 3.12, instalar explícitamente la dependencia
opcional en un entorno virtual usando el archivo fijado:

```sh
python -m pip install --require-hashes -r superhunter/requirements-owned-cross-evm.txt
```

No se descarga ni instala nada automáticamente al usar SuperHunter. El worker
comprueba versiones y bytes de 22 distribuciones (1,021 archivos de runtime)
antes de importar py-evm y vuelve a comprobarlos al terminar. Los hashes de rueda
fijan el material de instalación; no equivalen a una auditoría de esas dependencias
ni prueban que el host sea confiable. Las dependencias quedan fuera del repositorio.

El intérprete usa un prefijo de caché nuevo y privado por ejecución, además de
modo aislado y escritura de caché desactivada. `-B` por sí solo no evita leer una
caché anterior: una regresión ejecutable demuestra el caso con un módulo propio
y comprueba que el worker usa los bytes fuente.

Obtener el digest del checkout concreto y conservarlo externamente:

```sh
python -c 'from superhunter.quality import source_snapshot,sha; from superhunter.safe_io import canonical; print(sha(canonical(source_snapshot())))'
python -m superhunter compare-owned-evm-engines \
  --solc /herramientas/solc --evm /herramientas/evm \
  --source-digest DIGEST_VERIFICADO --out /privado/comparacion-nueva
python -m superhunter verify-owned-evm-engines \
  --solc /herramientas/solc --evm /herramientas/evm \
  --source-digest DIGEST_VERIFICADO --bundle /privado/comparacion-nueva
```

Los dos ejecutables deben satisfacer los pins existentes del proyecto. La
verificación vuelve a compilar y ejecutar **ambos motores**, además de comprobar
todos los bytes del paquete. No basta con recalcular un manifiesto alterado.
El worker de Python tiene límite de 180 s de pared, 90 s de CPU, 2 GiB de memoria
y 20 MiB por archivo (el compilador también se copia a un descriptor sellado).
La salida aceptada se limita a 4 MiB. Son límites de recursos, no un sandbox
general para código ajeno. La CLI solo acepta los controles propios fijos.

## Alcance de la evidencia

Las 144 llamadas no son 144 hallazgos ni casos estadísticamente independientes.
Siguen siendo cuatro variantes conocidas, dos positivas y dos negativas. Los
motores comparten compilador, código, escenarios y host. Se corrobora su ejecución
con dos implementaciones diferentes; no la independencia de productores.

No se comparan costes de gas, raíces completas de cuentas, operaciones de red,
firmas, inclusión de transacciones ni todos los opcodes del protocolo. El corpus
no es ciego y no demuestra generalización ni una vulnerabilidad original.

py-evm 0.12.1b1 es una implementación archivada. Se usa exclusivamente como
comparador histórico del perfil Cancun, nunca como certificado de reglas de
cadenas actuales. Véase el [anuncio de sus mantenedores](https://snakecharmers.ethereum.org/sunsetting-support-for-py-evm/).

Las pruebas unitarias del adaptador usan registros sintéticos identificados como
tales. Deben acompañarse de una ejecución nativa y su repetición para afirmar
que los dos motores se ejecutaron realmente.

## Alternativa de especificaciones ejecutables: EELS 2.20.0

`--second-engine execution-specs` selecciona el intérprete Cancun de Ethereum
Execution Specs en lugar de py-evm. La selección acepta solamente esos dos
adaptadores fijos y queda ligada al informe; la verificación exige volver a
seleccionar el motor correcto antes de ejecutar herramientas. No acepta rutas
de plugins ni bytecode externo.

Usar **otro entorno virtual** con CPython 3.12: la versión publicada de EELS
depende de cryptography 45.0.7, distinta de la 46.0.4 fijada para QA histórico.
No actualizar el entorno QA para acomodarla.

```sh
python -m pip install --require-hashes -r superhunter/requirements-owned-spec-evm.txt
python -m superhunter doctor-owned-lab --profile owned_cross_evm \
  --second-engine execution-specs --solc /herramientas/solc --evm /herramientas/evm
python -m superhunter compare-owned-evm-engines --second-engine execution-specs \
  --solc /herramientas/solc --evm /herramientas/evm \
  --source-digest DIGEST_VERIFICADO --out /privado/comparacion-eels-nueva
python -m superhunter verify-owned-evm-engines --second-engine execution-specs \
  --solc /herramientas/solc --evm /herramientas/evm \
  --source-digest DIGEST_VERIFICADO --bundle /privado/comparacion-eels-nueva
```

El adaptador verifica 23 distribuciones y 2,050 archivos antes de importar EELS;
usa su ejecución de creación/mensajes y sus primitivas de copia de trie, con
estado inicial restaurado por escenario y contexto transitorio nuevo por llamada.
La decodificación de almacenamiento usa cortes de bytes y se contrasta con la
decodificación por máscaras del otro adaptador. Conserva los límites de recursos,
la caché privada y las 144 llamadas del mismo corpus propio.

Son comparaciones **por pares contra Geth**. Ejecutar ambos adaptadores añade
una tercera implementación comprobada, no más casos independientes ni productores
autenticados. No certifica reglas actuales de red, consenso, tarifas, todas las
variables de bloque ni todos los opcodes. El alcance sigue fijado a estas
observaciones del perfil Cancun.

Referencias: [distribución 2.20.0](https://pypi.org/project/ethereum-execution/2.20.0/)
y [documentación del proyecto](https://steel.ethereum.foundation/docs/execution-specs/getting_started/installation/).
