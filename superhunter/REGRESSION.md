# Comparación de regresiones — incremento local, punto 48

## Estado y procedencia

Esta entrega integra el parche previo de privacidad sobre el código ejecutable
verificado del commit remoto `d3ab1a06b330e2d056114da91ff5f7b53d1304a7` del PR 35.
El conjunto de 30 archivos ejecutables, pruebas y políticas de esa base tiene
SHA-256 `22b0e2b791a70f53984a70beabd775508f3291c71674a71046002643eb379201`.
Se reprodujeron sus 224 pruebas antes de hacer cambios. La integración con las
36 pruebas de privacidad pasó 260 pruebas; el incremento completo pasa 300.

**Estado de publicación: cambio local preparado como parche, no publicado.**
Los archivos de validación previos conservan sus fechas y alcance histórico.
No se afirma que el registro antiguo de 209 pruebas describa esta versión.

## Qué ejecuta el componente

`regression.py` consume los paquetes producidos por `superhunter check` y no
lanza código, tests, contratos ni comandos suministrados por esos paquetes.
Lee los resultados individuales de pruebas ejecutadas, valida sus manifiestos
y exige las identidades SHA-256 esperadas de ambas versiones. Recalcula las
puertas de QA, las pruebas obligatorias y el inventario de componentes. No
confía solamente en una etiqueta `PASS` escrita en un documento.

La primera versión exige el mismo ejecutor y política de QA que el comparador
instalado. Protege por hash `quality.py`, `quality_worker.py`, `safe_io.py`,
`regression.py`, `privacy.py`, el catálogo y la dependencia del laboratorio.
Comprueba también la versión de Python registrada. Un paquete de una generación
anterior del ejecutor se rechaza: hay que repetir las pruebas con el mismo
harness, no renombrar su certificación ni sus hashes.

El resultado compara código cambiado, pruebas comunes, añadidas, eliminadas,
resultados FAIL/ERROR/SKIP y archivos de pruebas modificados. Un FAIL que pasa
tras eliminar o cambiar su archivo de pruebas NO constituye una corrección
acreditada por este módulo. El resultado de una prueba que cambia sin cambiar
el código queda bloqueado para investigar inestabilidad o diferencias de entorno.

La comparación es conservadora a nivel de archivo: cambiar una aserción, un
helper compartido dentro de `tests/` o eliminar una prueba puede bloquear la
comparación completa. No se busca aumentar artificialmente el número de éxitos.

## Veredictos

- `LOCAL_FIX_OBSERVED`: al menos un FAIL pasa con los archivos de pruebas
  existentes conservados, código de ejecución cambiado, QA posterior verde y
  ninguna condición bloqueante.
- `NO_REGRESSION_OBSERVED`: las pruebas registradas no muestran una regresión;
  no equivale a demostrar una nueva corrección ni seguridad universal.
- `REGRESSION_DETECTED`: una prueba antes aprobada ahora falla o produce ERROR.
- `COMPARISON_BLOCKED`: falta comparabilidad, desaparecen pruebas, cambian sus
  archivos, quedan resultados no aprobados u otra condición impide concluir.
- `COMPARISON_ERROR`: entrada malformada, identidad inesperada, artefacto alterado
  o error de lectura. Los diagnósticos no repiten datos de entrada.

Los detalles FAIL→PASS permanecen visibles aunque exista un bloqueo; el campo
`fix_observed` solo es verdadero para `LOCAL_FIX_OBSERVED`. Corregir un ERROR
no se etiqueta por sí solo como corrección de una vulnerabilidad.

## Uso

Primero ejecutar `check` en ambas variantes con el mismo conjunto de pruebas y
harness. Guardar las identidades de código que imprime cada ejecución. No usar
los hashes de Git del repositorio en los argumentos `--expect-*`: esos campos
son el SHA-256 de `source-snapshot.json` canonicalizado.

```bash
python3 -m superhunter compare-checks \
  --before /ruta/qa-anterior --after /ruta/qa-posterior \
  --expect-before SHA256_ANTERIOR --expect-after SHA256_POSTERIOR \
  --out /ruta/nueva-comparacion

python3 -m superhunter verify-comparison \
  --before /ruta/qa-anterior --after /ruta/qa-posterior \
  --expect-before SHA256_ANTERIOR --expect-after SHA256_POSTERIOR \
  --bundle /ruta/nueva-comparacion
```

El directorio de salida debe ser nuevo; contiene `comparison.json`,
`comparison.md` y `COMPLETE.json`. No se copian logs ni datos arbitrarios a los
informes. Los IDs y rutas se validan y los errores de argumentos se ocultan.
El código de salida es 0 para una comparación sin bloqueos, 1 para regresión o
bloqueo, 2 para error. **0 no significa plataforma segura ni Finding confirmado.**

La verificación relee ambos paquetes, recalcula el resultado y exige coincidencia
exacta. Editar el informe y recalcular sus hashes no basta para cambiar el veredicto.

## Corrección comprobada en esta entrega

Al integrar las dos ramas se identificó que `fuzz-lab` conservaba el parser
original de argumentos. Este repetía valores recibidos al rechazar un argumento
no conocido o un `--seed` inválido. Se añadieron dos pruebas con marcadores
sintéticos, sin credenciales reales.

Con las mismas 300 pruebas y el mismo harness, antes de modificar el parser:
**298 PASS y 2 FAIL**. Después de emplear `PrivateArgumentParser`: **300 PASS**.
El inventario antes/después muestra un único archivo cambiado: `fuzz_cli.py`.
No se modificó ninguna prueba entre ambas ejecuciones. El comparador y su
verificador, ejecutados en procesos separados, devolvieron `LOCAL_FIX_OBSERVED`,
con cero regresiones y cero pruebas eliminadas.

Identidades comprobadas:

- Antes: `706554277cc7e148b2dfc84094d80478307d536f34999033109ac87471c5a50f`.
- Después: `2c4d26e7e95a7a1f34d9984023aad3946f3bd5191e6ed2e2d85ae99945894b1d`.

El comparador añade 38 pruebas específicas; el parser añade dos regresiones.
Las otras 260 pruebas se conservan. La detección de secretos sigue siendo por
reglas finitas: no cubre todos los secretos posibles ni contenido visual.

## Límites que no se deben omitir

Los paquetes no llevan firma de un tercero independiente. Los hashes vinculan
bytes, pero un operador que controle código y artefactos podría falsificar un
conjunto consistente. Igualdad de archivos de pruebas tampoco prueba que toda
referencia transitiva o entorno externo conserve su comportamiento. El módulo
presenta observaciones locales bajo condiciones delimitadas, no una prueba
formal de seguridad.

No hay búsqueda, reproducción ni explotación de vulnerabilidades de terceros,
monitorización automática de parches externos, transacciones, RPC o envíos bounty.
No se ejecutó la suite histórica completa Rust/Python de NQC ni su verificador
completo de aislamiento; se verificó el subconjunto SUPERHUNTER y sus fuentes
nativas fijadas. No se ejecutó GitHub Actions. El punto 48 permanece **parcial**.

## Cambio remoto concurrente al cierre

La última lectura del PR mostró el HEAD
`adc28a062668de996848ace5d233d2fa055fbd4c`, que incorpora un nuevo centro de
revisión y declara 251 pruebas. Ese incremento remoto no se ha reconciliado
con este parche. Las 300 pruebas aquí registradas corresponden a la base
`d3ab1a06b330e2d056114da91ff5f7b53d1304a7` más privacidad y comparación de
regresiones. No se deben sumar ambos conteos ni reemplazar a ciegas el HEAD
remoto. El parche debe revisarse sobre su base exacta y posteriormente integrar
los cambios concurrentes conservando sus módulos y pruebas.
