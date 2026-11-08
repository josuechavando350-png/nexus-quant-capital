# Contrato cerrado para telemetría local de QA

El adaptador antes aceptaba texto libre en `error_type` al verificar un expediente
y escribía el nombre de clases de excepción definidas por el llamador. El SDK
podía heredar atributos de recurso del entorno; su captura automática de
excepciones podía registrar detalles de errores no manejados dentro de un span.

La implementación ahora comparte `otel_qa_schema.validate` entre el productor,
antes de escribir el expediente, y el verificador. Solo permite:

- Los campos declarados del perfil v1 o v2; dependencias v2 exactamente iguales
  a las identidades fijadas, incluidos los tipos numéricos.
- Contadores enteros entre cero y 2^63−1, sin aceptar booleanos o flotantes.
- Uno o dos spans con nombres fijos y duración; ningún atributo adicional.
- Estados coherentes de éxito o fallo, y digest hexadecimal minúsculo de 64
  caracteres en éxitos. Un éxito sigue requiriendo revalidar su expediente QA.
- Etiquetas de error de una lista cerrada. `error_label` clasifica por tipos
  incorporados, sin serializar el nombre de una subclase ni su mensaje.

El proveedor usa `Resource({})` explícito. Ambos spans desactivan
`record_exception` y `set_status_on_exception`. La proyección persistida sigue
conteniendo únicamente nombres fijos y duraciones; no contiene recursos,
atributos, eventos, IDs de traza, rutas o mensajes de excepción.

La CLI también normaliza las etiquetas de error. Los errores inesperados se
propagan a su llamador; no se convierten en un éxito ni dejan un expediente de
telemetría completo. Esta unidad no controla el manejo de errores que haga un
llamador externo ni promete limpiar cualquier traceback de la aplicación.

## Compatibilidad y alcance

Se conservan los nombres de perfil y formato existentes: la comprobación es más
estricta, sin promover v1 a v2. Informes antiguos con etiquetas de error fuera de
la lista o números mal tipados se rechazan deliberadamente. Los doce payloads
v2 del estudio anterior cumplen el contrato; esta revisión de esquema no vuelve
a certificar su código, tiempos o ejecuciones.

Las pruebas de privacidad usan valores sintéticos. Con SDK disponible capturan
spans reales sobre resultados QA simulados; esto se distingue de la ejecución
completa del QA real. Sin SDK prueban el bloqueo de dependencia, no simulan que
se ejecutó el SDK. No se instala un Collector ni se añade exportación de red.

El esquema no autentica al productor ni evita que un productor malicioso
codifique información dentro de un contador o digest válido. No se presenta
como garantía universal contra fuga de información o como hallazgo de terceros.

## Reproducción

En el entorno local previamente fijado, desde el checkout:

```sh
python3 -B -m unittest superhunter.tests.test_otel_qa_schema superhunter.tests.test_otel_qa superhunter.tests.test_otel_dependency_integrity superhunter.tests.test_quality_entrypoint -v
python3 -B -m superhunter profile-owned-qa --qa-out /privado/qa-nuevo --telemetry-out /privado/telemetria-nueva
python3 -B -m superhunter verify-owned-qa-profile --bundle /privado/telemetria-nueva --qa-bundle /privado/qa-nuevo
```

Usar directorios nuevos fuera del checkout. El perfil completo requiere las
ocho dependencias fijadas; el verificador independiente no necesita el SDK.

## Controles ejecutados

- 44 pruebas focales PASS con SDK real disponible, incluidas 17 nuevas.
- 17 pruebas nuevas PASS en otro entorno sin SDK: las rutas nativas comprueban
  bloqueo por dependencia; no se atribuye ejecución SDK a ese entorno.
- Comparación con el adaptador de `c2ab7c9ee0b4cbf0266ecf03defc1489521cc072`,
  usando SDK auténtico y QA simulado: antes se conservaba el marcador privado
  sintético en `error_type` y en el recurso; después no aparece en ninguno.
  Ambos lados conservan `QA_FAILED`.
- Los doce payloads históricos v2 cumplen el esquema. Los 227 archivos Python
  previos fuera de los tres archivos modificados conservan sus bytes; ninguna
  prueba anterior fue reescrita.

## Aceptación completa

QA real con SDK: **2,850 PASS**, cero fallos, errores o skips. Las 2,833
identidades anteriores permanecen en los mismos ocho grupos; 17 son nuevas.
QA, telemetría y preparación se verificaron desde otro proceso sin SDK. Una
revisión adicional cotejó los ocho recibos originales y reconstruyó el log
agregado byte por byte, comprobando fuentes y archivos otra vez al terminar.

Digest ejecutable: `4be4033a4757c919cc88fef6273bbf482ab2dd4c6cfa4909efdb7a87ccc18b25`.
Ancla QA: `f913632cbd2210a554d61643426be481fa1cbdbdef159dc854823051ed89109e`.
Ancla telemetría: `a6ebb83af6b41b94dd1416fdc85509faddc273004f7bf593bf2ff176ed6fe5f5`.
Mayor tiempo observado por worker: 84.197994 s;
límites originales intactos. Esta corrida no es un estudio de rendimiento.

Límite de repositorio PASS; 642 archivos históricos intactos. Los perfiles
nativos Slither/Geth/EELS no se reejecutaron: sus aceptaciones previas siguen
asociadas a sus digests originales. Rust/PFT/Census no recertificados.

Evidencia: `SUPERHUNTER_TELEMETRIA_ESQUEMA_CERRADO_20261108.zip`.
