# Verificación enlazada y estado comprobable

## Entrega y límites

Se añade una puerta única de calidad local, no un Hunter autónomo. Ejecuta las
pruebas reales del proyecto, los componentes numéricos DIABLO/NQC existentes y
una comprobación en un segundo proceso. Ningún resultado de este recorrido
certifica ausencia general de vulnerabilidades ni autoriza pruebas a terceros.

El código nuevo no implementa las 50 capacidades solicitadas. `capabilities.py`
conserva los 50 identificadores, dependencias y restricciones; `CHECKLIST.md`
separa los fundamentos verificados de esos módulos pendientes. El catálogo es
una especificación versionada, no cincuenta clases vacías ni motores simulados.
Las solicitudes de evasión, extracción de secretos y explotación autónoma se
registran como rediseño defensivo pendiente, no como funciones aprobadas.

## Un comando, cinco etapas

```bash
python3 -m superhunter verify-project --out /tmp/superhunter-verification-001
python3 -m superhunter verify-project-bundle --bundle /tmp/superhunter-verification-001
```

1. `source_pins`: inventario de fuentes y comprobación de los cuatro componentes nativos.
2. `regressions`: ejecución aislada de la suite propia; registra cada test por identificador.
3. `native_execution`: ejecución efectiva del laboratorio local con sus cinco casos.
4. `independent_check`: verificación en otro proceso y recálculo de la referencia numérica.
5. `capability_checklist`: palomitas de fundamentos únicamente con los tests obligatorios y todas las puertas aprobadas.

Cada etapa contiene hashes de sus evidencias, la misma versión del código y los
recibos de sus dependencias. No acepta nombres de comandos, plugins, endpoints,
objetivos o PoCs externos. Una etapa fallida bloquea las posteriores y conserva
el diagnóstico disponible. Test omitido, resultado esperado de fallo, prueba no
ejecutada o recuento incompleto impiden aprobar la suite.

Las pruebas usan subcasos deliberadamente fallidos para verificar el control de
fallos; esos subcasos no son resultados omitidos o fallidos de la suite exterior.
El worker de QA ejecuta código propio confiado, no es un sandbox para código
hostil. Los límites y restricciones del worker numérico siguen en LOCAL_LAB.md.

## Dos defectos corregidos, comprobados antes y después

En la versión base se podían aceptar artefactos consistentes en sus hashes pero
inconsistentes en su significado: una declaración de ejecución local falsa y
una entrada de bitácora asociada a otro caso. Se reprodujeron ambos problemas.
Las mismas dos pruebas de rechazo fallan sobre la versión anterior y pasan
sobre la corregida. `lab_integrity.py` verifica ahora la secuencia completa,
identidad de cada caso, entradas, resultados, alcance local, tipos y tiempos.

Esto no autentica a un productor remoto que controla el paquete completo:
recalcular todos los hashes nunca constituye una firma independiente. Se exige
consistencia semántica y numérica, sin prometer inmutabilidad ni autoría remota.

## Evidencia de esta ejecución

Base revisada: `665728368468988204d43cbfb7c06f2c8502059f`.
Los 23 archivos de la copia local se cotejaron con el árbol Git remoto.
Baseline: 102 tests aprobados. Suite final: **139 tests, cero fallos, errores,
omisiones, expected failures o unexpected successes**. Los cinco casos locales
pasaron y el paquete se volvió a verificar en un proceso separado.

El paquete de ejecución contiene el resultado por test, log, snapshot de fuentes,
recibos de etapas, cálculos NQC, bitácora DIABLO y checklist. Su resultado es
`LOCAL_QUALITY_PASS`; la revisión posterior devuelve `QUALITY_BUNDLE_CONSISTENT`.
Ninguno significa vulnerabilidad confirmada o seguridad perfecta.

No se ejecutaron Forge, contratos, forks, RPC ni investigación de sistemas de
terceros. Tampoco se ejecutaron la suite histórica completa de NQC, su verificador
completo de aislamiento o GitHub Actions. Las fuentes nativas originales y los
árboles históricos permanecen fuera del alcance de las modificaciones.

## Retomar el trabajo sin perder el contexto

La fuente del estado de las 50 capacidades es `capabilities.py`; una edición de
estado no puede promover una capacidad a implementada. Para añadir un motor
real se necesita una revisión de código, pruebas de aceptación propias y actualizar
el contrato del catálogo, nunca sustituir PENDING por COMPLETE en un JSON.
Los fundamentos F01–F05 tienen IDs de tests obligatorios. Su aprobación depende
de la ejecución concreta, no de una palomita escrita en documentación.

Los resultados se guardan en carpetas nuevas y privadas, fuera del checkout.
El verificador exige el mismo snapshot de código: un resultado de una versión
anterior no certifica una modificación posterior. Los manifiestos son evidencia
local sin firma; el estado de producción sigue sin certificar.
