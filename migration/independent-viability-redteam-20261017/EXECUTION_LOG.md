# NQC — Registro de ejecución independiente / Directiva 002

Fecha: 17 de octubre de 2026. Todos los momentos técnicos se expresan en UTC. Este registro distingue acciones observadas, resultados de archivos anteriores y trabajo no ejecutado. No pretende reconstruir segundos de captura que no se registraron.

## 1. Alcance ejecutado

- Lectura de la directiva adjunta, AGENTS.md y referencias GitHub autorizadas.
- Investigación finita de documentación pública primaria de patrocinio, ERC-4337, admisión y temporalidad.
- Reconciliación contable propia, auditoría de registros guardados, filtros del censo y análisis de tiempos.
- Comparativa G1–G5, sensibilidad condicional y búsqueda histórica acotada de magnitudes.
- Escritura de documentos y scripts sin red bajo la carpeta independiente permitida.
- Preparación de publicación en rama separada derivada de la rama de auditoría, condicionada a preservar todos los archivos originales. El resultado concreto se registra en PUBLICATION_RECEIPT.json de la entrega, no se presupone en este registro previo al commit.

Los análisis paralelos internos son parte de esta sesión. No se enviaron mensajes al director externo ni al chat Astra. No se recibieron sus resultados posteriores.

## 2. Adquisición e integridad

| Trabajo | Resultado y alcance |
| --- | --- |
| Cinco HEAD iniciales | Coincidieron con la Directiva 002; evidencia en baseline_heads.json. Primera ventana de consulta 15:39–15:44 UTC; no se conservaron segundos individuales. |
| AGENTS.md | Leído al SHA de auditoría; blob 6c2fe3771bad272bb1839aabc2b45ef636a16531, 1107 bytes. |
| Árbol Git base | Consulta recursiva completa, 768 entradas, no truncada. Commit padre ddade5d099e19449e0c4e55079a2b0c9d9ee1141; tree declarado por el commit 840387bcd4c887ecc13005148dec44585ecb021f. |
| Fuentes contables | Snapshots necesarios guardados en accounting_inputs.json; verificación independiente de blobs cuando el contenido era completo, con la limitación del extracto declarada. |
| Fuentes del censo | 46 JSON, 517006 bytes, verificados por Git blob y SHA-256; manifiesto de procedencia adicional. |
| Documentación web | Fecha de consulta por lote en los módulos de fuentes; una página vigente no prueba su contenido histórico. No se redistribuye el HTML completo. |
| Índice unificado | SOURCE_LEDGER.json conserva 133 registros y referencias verificables a cuatro módulos, con 128 IDs originales únicos y cinco IDs de índice para objetos sin ID. |
| PDF maestro ausente | NQC_RELEVO_MAESTRO_2026-10-17.pdf no fue adjuntado ni leído. |
| Archivo T37 | Se leyó cierre y metadatos del artifact; no se descargó el ZIP binario. Los metadatos no se presentan como lectura de datos crudos. |

La respuesta recursiva original conserva en su campo sha la referencia consultada del commit. El SHA real del árbol base se tomó del objeto commit; no se confundieron ambas referencias al preparar Git Data.

### Corrección del caché de fuentes

Una escritura inicial mediante patch añadió un LF final adicional a algunas copias locales. El cotejo de Git blob detectó el desajuste. Se restauraron bytes exactos desde las respuestas originales conservadas y sólo se corrigió un LF cuando el resultado coincidía con el blob esperado. No se normalizó ni alteró el contenido fuente arbitrariamente. Los insumos finales del censo pasan sus 46 verificaciones. El verificador original de aislamiento se volvió a ejecutar tras corregir sus bytes y siguió bloqueado por el mismo payload ausente.

## 3. Accesos fallidos o límites conservados

| Acción | Resultado | Tratamiento |
| --- | --- | --- |
| Tres lecturas de ramas con slash codificado | 400 / INVALID_ARGUMENT del validador de URL | Se usó la colección oficial soportada de ramas. No era un RPC denegado ni se ampliaron permisos. |
| Clon HTTPS | Salida 128; proxy del entorno no accesible | No se reintentó ni se escaló. El conector GitHub disponible permitió lectura y Git Data. |
| Primeras aperturas de algunas páginas Quasar/Robinhood | Fallo de recuperación de la herramienta | Se conservaron errores y se usaron las URLs oficiales o referencias ya recuperadas que los módulos identifican; no se eludió autenticación. |
| Rechazos RPC 403/405, método no admitido o estado podado del expediente anterior | Respuestas históricas guardadas | No se repitieron estos RPC; no se cuentan como nuevos errores de red de esta misión. |
| Verificador original de aislamiento | Salida 1 por archivo de payload ausente | BLOCKED_INPUTS; no PASS, no fallo económico, no certificación de la importación completa. |

Los detalles de los dos errores web del módulo sponsor están en evidence/sponsor_sources.json, y los del módulo temporal permanecen en sus registros. No se hizo un bucle de búsqueda o reintento después de una denegación.

## 4. Pruebas propias realmente ejecutadas

Entorno de validación final: Python 3.12.14. Directorio de trabajo: migration/independent-viability-redteam-20261017/ del paquete.

### Reejecución final del coordinador

Inicio registrado: **2026-10-17T16:13:33.169Z**. Finales: **16:13:33.431–16:13:33.436Z**.

| Comando | Resultado | Qué certifica |
| --- | --- | --- |
| PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_accounting_audit | Salida 0; 25 tests OK | Guardrails, aritmética entera, límites, propagación de UNKNOWN, identidad y anti-doble-conteo sobre entradas guardadas y casos hipotéticos |
| PYTHONDONTWRITEBYTECODE=1 python3 accounting_audit.py --output /tmp/nqc-root-accounting-recheck.json | Salida 0; T-01…T-10 PASS | Reconciliación de los artefactos guardados y cota contable; elegibilidad NQC UNKNOWN |
| PYTHONDONTWRITEBYTECODE=1 python3 census_audit.py --output /tmp/nqc-root-census-recheck.json | Salida 0; 12 grupos OK; 46 blobs | 143 eventos/141 tx, filtros, selección, control positivo y tiempos; admisión UNKNOWN_NOT_TRUE |

Los comandos y outputs completos están en evidence/final_validation.json. La suite de 25 incluye los diez guardrails: **no se suman 25 + 10 como 35 pruebas independientes**. Los 12 grupos del censo son otra unidad de comprobación, no doce pruebas EVM.

Se conservaron además las ejecuciones de elaboración en evidence/accounting_test_output.txt y evidence/census_execution.txt. Ejecutar dos veces una suite no duplica el número de pruebas distintas. Los modelos S1–S5 del módulo sponsor incluyen diez comprobaciones de conservación sintética documentadas, sin convertirlas en fallos reales observados.

### Verificador original

Comando realmente intentado:

```sh
python3 migration/verify_isolation.py --root /workspace/scratch/8e92c6d61919/nqc-isolation-inputs
```

Resultado guardado:

```text
ISOLATION_FAILED: [Errno 2] No such file or directory:
'/workspace/scratch/8e92c6d61919/nqc-isolation-inputs/ci/migration/legacy-workflows/nqc-build-truth-closeout.yml.disabled'
```

Salida 1. La copia parcial no contiene todos los payloads requeridos. Estado **BLOCKED_INPUTS**. No se descargaron 637 payloads sólo para afirmar una certificación de importación en una adición documental. No se ejecutó ni aprobó la suite original de nueve pruebas.

### No ejecutado

No se corrieron replays EVM/Foundry/Solidity/Rust, pruebas originales de Astra, consultas RPC nuevas, simulaciones remotas de bundles, admisión ERC-4337 real ni el protocolo temporal futuro. No se inspeccionó consenso onchain ni se autenticó un storage root nuevo. No hubo captura de una liquidación propia.

## 5. Error contable propio corregido antes de publicar

La revisión manual final detectó que los decimales Robinhood del README se habían transcrito a wei con escala 1000 veces menor. Los valores originales del README eran correctos:

| Campo | Transcripción inicial incorrecta | Wei correctos |
| --- | ---: | ---: |
| Cargo paymaster | 79616762214 | 79616762214000 |
| Comisión nativa Nitro | 57601054408 | 57601054408000 |

El control inicial de 24 tests había aprobado sus inputs mal transcritos. La detección fue **revisión manual, no un test fallido**. Se preservó íntegra aquella salida bajo SUPERSEDED, se corrigieron inputs y documentos, y se añadió una prueba que extrae el decimal desde la fuente preservada y calcula Fraction(texto_decimal) × 10**18, incluyendo un caso negativo contra la escala anterior. La salida final registra **25 tests PASS**.

La diferencia correcta es 22015707806000 wei, equivalente a 0.000022015707806 ETH. La suma duplicada incorrecta como coste de un perímetro consolidado sería 137217816622000 wei. No se modificaron las fuentes de Astra ni el caso B. La corrección figura en INDEPENDENT_ECONOMIC_LEDGER.md, accounting_inputs.json, accounting_test_output.txt y S-R-06.

## 6. Publicación y trazabilidad

Sólo se permite añadir rutas dentro de migration/independent-viability-redteam-20261017/. FILE_MANIFEST.json enumera paths, bytes, SHA-256 y Git blob, excluyéndose a sí mismo para evitar circularidad. verify_publication.py compara todos los archivos originales y sus modos contra el árbol candidato, exige el conjunto exacto de adiciones y comprueba sus blobs contra los bytes locales.

El árbol no contiene workflows activos. No se añaden configuraciones CI/deploy, no se habilitan los workflows desactivados y no se modifica otro árbol de producto. Un mensaje de commit con [skip ci] es sólo una precaución adicional, no la prueba de aislamiento. La prueba principal es el contenido del árbol y la lectura posterior de los HEAD originales.

Después del commit se registra fuera de su propio contenido un PUBLICATION_RECEIPT.json con SHA, padre, tree, rama, paths/bytes, resultado de read-back y HEAD posteriores. Esa separación evita pretender incluir en un commit su propio SHA. La entrega no afirma push hasta contar con ese recibo.

## 7. Coste y acciones externas

**Gasto externo iniciado por las acciones de esta misión: $0.** La constatación corresponde al inventario de acciones: no hubo compras, suscripciones, nuevas cuentas de proveedor, tarjeta, firma, transferencias, despliegues, contacto comercial ni solicitudes de operaciones reales. No se auditó la facturación histórica del usuario ni se hace una afirmación sobre costes preexistentes fuera de esta misión.

Se mantuvieron sin cambios las restricciones de capital personal cero, deuda cero y ausencia de garantías/reposición. Las lecturas públicas y comprobaciones locales no se presentan como aceptación, financiación o ingresos NQC.
