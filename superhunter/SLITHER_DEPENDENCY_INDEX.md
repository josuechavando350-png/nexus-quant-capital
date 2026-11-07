# Índice visible de dependencias Slither

El perfil `owned-slither-separated-wheels-visible-index-v2` añade una condición al inventario de archivos fijados: todas las distribuciones visibles para `importlib.metadata` deben ser exactamente las 51 previstas, cada una en su directorio dedicado. No instala paquetes ni cambia versiones, wheels, fuentes propias o límites.

## Fallo reproducido y corrección

El checker anterior revisaba sus directorios, pero no el índice completo de distribuciones visible por las rutas Python. Una prueba propia añadió únicamente un directorio temporal con METADATA de `owned-metadata-control`. Había 52 distribuciones visibles y el checker seguía admitiendo sus 51 pins. No contenía módulos, payload o entry points y no ejecutó Slither ni cambió el entorno instalado.

La comprobación nueva rechaza la ubicación extra antes de leer sus metadatos. También exige cardinalidad exacta, ausencia de duplicados, nombre normalizado y versión coherentes con el directorio fijado. Vuelve a comprobar el índice después de los dos recorridos de archivos, para detectar cambios durante la revisión. La normalización de nombres permite las equivalencias estándar de mayúsculas, guiones, puntos y guiones bajos; no admite nombres malformados.

| Control con entorno real | Resultado |
|---|---|
| 51 distribuciones originales | admitidas |
| Las mismas 51 + METADATA propio externo | rechazado: `SLITHER_DEPENDENCY_IDENTITY_INDEX_LOCATION` |
| Retirar solo la ruta temporal | vuelven a admitirse las 51 originales |

Los 51 wheels, 2,313 archivos derivados, sus hashes y el archivo de rutas `.pth` permanecen idénticos. El perfil conserva `producer_authenticated=false` y `process_memory_integrity_proved=false`.

## Validación

Ocho regresiones nuevas, además de las 37 pruebas Slither anteriores: **45 focalizadas PASS**. Antes del cambio se ejecutaron 14 pruebas de dependencias; aparecieron diez fallos contabilizados, incluidos subtests de nombres inválidos. Se conservan esos fallos y el control real previo. **2,654/2,654 QA PASS**, cero fallos/errores/skips, SDK real y verificador separado sin SDK. Se retienen las 2,646 identidades previas en sus workers y se añaden ocho. Ocho workers y límites originales intactos; máximo 73.418816 s. Digest `5807558e4e8866ebefa5606e3560aabe2530c367fdf1549de5473e95233dc41a`.

Con ese mismo digest, Slither real y replay separado: TP 1/TN 2/FP 0/FN 0. Aceptación conjunta Geth/EELS y verificador separado: cuotas TP 4/TN 2/FP 0/FN 0; autoridad TP 6/TN 4/FP 0/FN 1. La omisión latent_revocation se conserva. Aceptación 116.804 s, verificación 58.291 s; denominadores separados. Límite de repositorio PASS y 642 archivos históricos preservados. Rust histórico no reejecutado.

Esto cierra el índice de distribuciones, no todos los mecanismos de importación Python. No autentica el intérprete, stdlib, módulos previamente cargados, modificaciones de memoria o código ejecutado durante el arranque de Python. No es un sandbox completo del host ni una certificación de integración para producción. Los procesos de aceptación continúan usando cachés privados nuevos y las fuentes propias fijas; no se habilitan destinos externos. Avance global no determinado; ninguna vulnerabilidad original confirmada.

Referencia de formato y normalización: [Python Packaging User Guide](https://packaging.python.org/en/latest/specifications/name-normalization/). Un entorno que añada pip u otras distribuciones visibles también queda fuera del inventario cerrado de este perfil; no se incluyen paquetes de instalación por conveniencia.
