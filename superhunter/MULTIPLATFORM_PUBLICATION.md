# Frontera de esta publicación

Esta rama es un incremento focalizado sobre PR40, commit
56038908d0487b91994f9060afa5b2051b5558a6. Publica el registro de programas,
sus 49 pruebas, rutas CLI, registro en QA y documentación. Su suite tiene
378 pruebas ejecutadas. No se sustituyen las fuentes históricas de NQC.

La entrega local acumulativa es distinta: combina contabilidad, enlaces Python
y Z3, preservando 718 identificadores previos y añadiendo las 49 pruebas nuevas.
Esa versión pasó 767 pruebas y el recorrido conjunto, seguido de verificación
en otro proceso. Sus 27 requisitos, 50 capacidades y 25 iniciativas se conservan.
**La consolidación local completa NO está publicada íntegramente aquí.**
No usar esta rama menor para reemplazar el paquete acumulado.

Las ocho plataformas son etiquetas de un registro local, no cuentas conectadas,
APIs implementadas ni programas inscritos. El ensayo utilizó 20 programas
explícitamente sintéticos. Un resultado ELIGIBLE_LOCAL_REVIEW prepara revisión
local con reglas declaradas; no autentica autorización ni permite ejecutar
pruebas o enviar reportes. Cambios de políticas, exclusiones y caducidad bloquean
el expediente hasta su revisión. Siete días es un límite local, no una regla
atribuida a plataformas externas.

Los diez frentes de ampliación se conservaron como plan en MULTIPLATFORM.md.
Este incremento no implementa los diez motores ni garantiza detección total,
cero falsos positivos o superioridad frente a herramientas existentes.

Se verificaron los blobs de código/tests/documentación contra los archivos
probados. Los hashes acreditan bytes, no permisos de un tercero. No se ejecutaron
la suite histórica completa de NQC, el verificador global de aislamiento ni
GitHub Actions. No hubo llamadas a plataformas de bounty, escaneo, EVM, PoCs,
Slither/solc/Forge, firma, fondos ni envío automático de reportes.
