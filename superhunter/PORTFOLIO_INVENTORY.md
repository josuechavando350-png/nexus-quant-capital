# Inventario verificable de los cuatro registros

Continuación del PR #87, commit `7a57b3538218a4f981ef5001f35f764be0b467b2`.
Se añade un lector y verificador del catálogo externo, junto con un informe
que mantiene separados los cuatro registros estructurados. El módulo es de
lectura local: no descarga, instala, importa ni ejecuta los proyectos listados.

## Consistencia del catálogo externo

`repo_portfolio_50.json` debe contener las 50 identidades únicas y ordenadas.
Cada uno de los cinco archivos de `repo_portfolio/` debe coincidir exactamente
con sus diez entradas canónicas, incluidos sus textos, campos y estados.
Los archivos se eligen por rutas fijas del programa, nunca por una ruta
modificada dentro del JSON.

Se comprueban esquema, tipos estrictos, fecha, política documental, rangos,
estados, prioridades y campos obligatorios. Las referencias deben tener forma
`owner/repository` y URL GitHub coincidente; los duplicados se detectan sin
distinguir mayúsculas. La comprobación es sintáctica, no una consulta de
existencia, propiedad o licencia del repositorio remoto.

Los seis archivos del portafolio pasan a formar parte de `source_snapshot`
y del componente QA `portfolio_inventory`. Sus bytes originales se conservan.
Ahora un cambio en esos datos cambia el digest de QA; una aceptación de una
versión anterior no se traslada automáticamente a datos nuevos.

El lector compara los bytes antes y después de validarlos. El informe exige
que todos sus nueve catálogos de origen estén ligados al inventario del código.
El verificador regenera el resumen y vuelve a comprobar fuentes, inventario y
bytes. Los hashes no autentican un productor independiente.

## Qué significan los conteos

| Registro | Elementos | Estados declarados actuales |
| --- | ---: | --- |
| Requisitos de integración | 27 | 12 implementados con límites, 3 parciales, 12 pendientes |
| Capacidades internas | 50 | 9 parciales, 24 planeadas, 17 requieren rediseño |
| Iniciativas | 25 | 5 parciales, 20 planeadas |
| Repositorios externos candidatos | 50 | 50 `CATALOGUED_NOT_INTEGRATED` en el catálogo histórico |

Los tres registros internos se validan con sus lectores existentes, sin
reescribir sus estados. Los números son **declaraciones del registro**, no
una nueva evaluación de implementación. El informe no consume recibos de QA,
pruebas nativas, autorizaciones o revisiones de licencia para elevar un estado.

El catálogo externo es una instantánea documental. Su estado no prueba que
una herramienta esté instalada o ausente hoy; la evidencia posterior de cada
laboratorio tiene su identidad y alcance propios. En particular, el SDK
OpenTelemetry usado para QA no acredita la integración del OpenTelemetry
Collector que figura como candidato #26.

Las listas se solapan y tienen unidades distintas. El módulo no las suma,
no cuenta las propuestas adicionales del plan maestro como implementación
y deja `global_progress` en `null`. Tampoco infiere autorizaciones operativas
a partir de una URL o de texto de política.

## CLI y evidencia

Desde el checkout, con una salida nueva fuera del repositorio:

```sh
python3 -B -m superhunter review-registry-inventory --out /ruta/privada/inventario
python3 -B -m superhunter verify-registry-inventory --bundle /ruta/privada/inventario --expected-source DIGEST_ESPERADO
```

El bundle contiene `inventory.json`, `REVIEW.md` y `COMPLETE.json`. Conserva
las identidades y estados declarados de cada registro, junto con los SHA-256
de sus nueve archivos de origen. La CLI solo lee los catálogos del checkout.

## Regresiones

32 pruebas focalizadas PASS. Se comprueban IDs y repositorios duplicados,
booleanos usados como números, campos faltantes/adicionales, desgloses
inconsistentes, modificaciones de política, intentos de promoción documental,
URLs/rutas fuera del formato, JSON con claves duplicadas, symlinks, cambios
durante la lectura y resúmenes falsos con manifiestos recalculados.

La creación y verificación de CLI se ejecutan en procesos separados. El
resultado global de QA y sus aceptaciones nativas se registra para el digest
de esta versión en `CONTINUATION.md`; las 32 pruebas focales no sustituyen
esa validación integral.
