# Diferencial nativo entre tres configuraciones de compilación

Este módulo comprueba regresiones de los tres contratos aritméticos PROPIOS
ya incluidos en SUPERHUNTER. No analiza objetivos externos, no descubre exploits
ni recibe fuentes, calldata, flags de optimización o RPC suministrados por usuario.

## Entrada y ejecución

Requiere una aceptación creada con `review-native-platform` por la misma versión
del código. La huella esperada se conserva fuera del paquete. El comando verifica
QA y vuelve a ejecutar solc/Z3/EVM de la aceptación antes de usar sus resultados.
No repite las pruebas QA por el mero hecho de verificar su recibo.

```bash
python3 -m superhunter review-native-platform \
  --solc /ruta/solc --evm /ruta/evm --out /privado/aceptacion-nueva

python3 -m superhunter review-compiler-variants \
  --acceptance /privado/aceptacion-nueva --expected-source HUELLA_EXTERNA \
  --solc /ruta/solc --evm /ruta/evm --out /privado/variantes-nuevas

python3 -m superhunter replay-compiler-variants \
  --bundle /privado/variantes-nuevas --acceptance /privado/aceptacion-nueva \
  --expected-source HUELLA_EXTERNA --solc /ruta/solc --evm /ruta/evm
```

`HUELLA_EXTERNA` es un marcador de documentación, no un valor válido. Debe ser el
SHA-256 del inventario esperado de fuentes/políticas de esta versión. Los binarios
son exactamente los pins existentes: solc 0.8.30 y Geth evm 1.17.10, Cancun sintético.
No se descargan herramientas ni se incluyen binarios en la entrega.

Perfiles fijos:

1. `legacy_unoptimized`: código directo, sin optimizador; aceptación original.
2. `legacy_optimized`: código directo, optimizador habilitado, runs=200.
3. `ir_optimized`: generación vía Yul IR, optimizador habilitado, runs=200.

Solo cambian optimizer/viaIR. Las fuentes, ABI, selector, layout y ambiente EVM
son los mismos. Los metadatos deben reflejar el perfil realmente solicitado.
Se ejecuta un constructor y seis llamadas por control/perfil: 9 creaciones y
54 llamadas en total por recorrido. Las seis compilaciones adicionales ejecutan
el worker existente y mantienen sus límites. El tiempo total de la aceptación
incluye más procesos; no se presenta como el presupuesto anterior.

## Comparación y contabilidad

Cada constructor comienza en vacío y debe producir SU runtime. Cada llamada
recibe el estado real de la anterior y debe conservar exactamente el presupuesto
de gas fijado. Se reparsan las salidas nativas, se comprueban los balances,
nonces y almacenamiento completo del perfil, además de retornos y errores.
El conciliador existente contrasta unidades internas mediante enteros y Decimal.
No se registran como aplicados los movimientos de llamadas revertidas.

El bytecode cambia por diseño: se conservan sus bytes/hashes, pero NO se exige
igualdad de código, codeHash o raíz del trie entre configuraciones. La proyección
observable omite únicamente esas identidades del código. Los cálculos EVM de
consumo de gas no se recogen aquí; no se afirma equivalencia de gas, todo input,
toda secuencia ni todos los presupuestos. Se comprueba el límite normal existente
y el control negativo fijo de un gas, no una curva de gas exhaustiva.

El resultado `FIXED_COMPILER_VARIANTS_AGREE` acredita igualdad observada de los
controles declarados. No identifica un defecto del compilador, transfiere pruebas
formales de fuente al bytecode, certifica upgrades ni implica seguridad universal.
Son configuraciones del MISMO compilador en la MISMA EVM, no implementaciones
independientes. Solidity documenta diferencias semánticas entre rutas para otras
construcciones; esta comparación NO se generaliza a contratos arbitrarios.

## Evidencia y errores

`variants.json` conserva entradas, salidas de compilador y observaciones EVM de
los perfiles adicionales. El baseline y QA permanecen en la aceptación externa,
ligados por hash. `comparison.json`, `audit.json` y `REVIEW.md` son derivados.
Los originales nunca se modifican. El paquete no se valida por sí solo: requiere
la aceptación original, código esperado y binarios. No ofrece modo de éxito
estático cuando falte una herramienta.

El replay reconstruye las fuentes y configuraciones desde el código fijo;
NUNCA compila fuentes o consultas tomadas de variants.json. Vuelve a verificar
la aceptación nativa y a ejecutar los perfiles extra antes de comparar todos
los archivos. Una interrupción, desacuerdo o insumo omitido bloquea el éxito.
Exit 0 significa concordancia observada; exit 2 significa rechazo o fallo.
No hay fallback silencioso ni parámetro para añadir objetivos.

La bitácora nativa DIABLO une aceptación, código y resultados. Los hashes y una
bitácora no autentican la verdad de un productor remoto. Los archivos privados
usan 0600 y las carpetas 0700; no sobrescribir ni publicar evidencia sensible.

## Pruebas y referencias

La captura de tests procede de una ejecución nativa real de desarrollo. Leerla
no equivale a recompilar. Los tests de orquestación usan sustitutos explícitos;
la aceptación CLI se ejecuta separadamente, sin mocks. El resultado total de la
entrega se registra fuera del código, en VALIDATION.json y los logs originales.

Referencias primarias consultadas:
https://docs.soliditylang.org/en/v0.8.30/using-the-compiler.html
https://docs.soliditylang.org/en/v0.8.30/ir-breaking-changes.html

Las capacidades 27/50/25 no se elevan a completas. Este laboratorio amplía la
comprobación de los propios controles; no demuestra descubrimiento autónomo.
