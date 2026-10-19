# NQC 666 R6 — entrada verificable preparada; optimización no promovida

**Resultado:** se incorporó el adaptador offline de capturas al motor R5 y se preservaron sus defensas. La optimización ensayada NO sustituye a R5: la confirmación encontró regresiones de máximos y un descarte adicional. **No se completó la integración con un testigo auténtico**, porque los artefactos disponibles no contienen las pruebas necesarias. No está certificado el bot completo.

Base: `205015f4941abaad2c3102a4dbffd4e980f62196`. Rama aislada `research/nqc-666-third-eye-20261018`; solo adiciones R6. main y R0–R5 permanecen intactos.

## Trabajo implementado

- Adaptador de cuatro respuestas JSON-RPC de lectura: cadena, encabezado por hash, runtime y prueba de cuenta/nueve slots. No envía solicitudes. Correlación estricta de IDs, errores/cobertura/duplicados, bloque/cadena/punto de estado y normalización limitada del ancho de claves.
- Integración con R5, cálculo Rust R1/R4 y gateway con identidad, expiración, plazos, revocación y puerta comercial cerrada. El tiempo de adaptación queda dentro del presupuesto del ingreso.
- Importador/planificador offline que conserva bytes y hashes, registra rechazo y elimina hechos parciales si falla una etapa. Plan emitido y root-binding verificado se distinguen expresamente.
- Dos hipótesis independientes: A evita serialize/parse repetido; B acelera hex manteniendo su aceptación canónica. Se midieron baseline, A y A+B; los candidatos quedan únicamente para reproducir el experimento. API/CLI usan baseline.

La arquitectura mantiene un propietario/hilo del gateway y roles lógicos de estado e integridad de datos. No se añaden servicios, agentes, procesos ejecutores, concurrencia ni dependencias. No se tocan financiación NQC031 ni auditoría NQC032.

## Evidencia auténtica pendiente

La revisión del paquete `NQC_031_R2_NET_ADAPTADOR_Y_ESTADO.zip` encontró una captura parcial de **chainId 4663**, no un testigo autenticado Ethereum. Se verificó la integridad de sus 151 archivos; eso no prueba verdad de cadena. El propio informe declara raíz pretransacción null, 0 pruebas de cuenta/storage verificadas y 11 lecturas desconocidas. No se ejecutaron sus contratos ni se sustituyeron esos datos por cero.

Archivo original SHA256: `6f5e67ce8f1ab7504366a1abb36ece43ffbe2739804b6176e817e2156c92873d`. Los tres documentos técnicos seleccionados se conservan sin modificar en reference, con hashes y procedencia. El inventario de ramas no mostró un nuevo testigo publicable; la búsqueda suplementaria por títulos no fue un examen exhaustivo de todo el archivo. No se reintentó la solicitud RPC que recibió 403 en R4 ni se buscó eludirla.

El motor actual soporta chainId 1/end_of_block. La raíz padre o final de cadena 4663 no es la raíz intermedia anterior a tx1. No se cambia la cadena de una captura para hacerla pasar. WITNESS_REQUIREMENTS.md especifica el testigo Ethereum que admite este motor y delimita el frente Nitro pendiente.

## Medición y decisión

135.168 ventanas individuales en total, repartidas en dos matrices conservadas por separado. Cada variante recibe la misma entrada y se rota/alterna el orden. CPU AMD EPYC 9V74 bajo KVM, afinidad CPU 0, GC habilitado, Python 3.12.14, Rust 1.90.0/LLVM20.1.8, O3/fat LTO sin cambio. Frecuencia/carga/IRQ del host no controladas; no se atribuyen los picos a la VM sin evidencia.

Corpus **sintético**: 16 paquetes R3 (árboles con poblaciones 0/16/64/256), 13 precios condicionales, código de fixture que no es Morpho desplegado. No se presenta como testigo real ni como distribución representativa de todo Ethereum. La ventana empieza con JSON completo en memoria: incluye parseo, adaptación, prueba y, en ingreso, reset/ticket/escenario/puerta cerrada. No incluye red, archivo, builder, oráculo/IRM ni EVM.

El baseline aquí es R5 **detrás del mismo adaptador de captura**. No se compara directamente con el 1,40 ms previo de R5, que tenía otra frontera de entrada. Todos los tiempos, descartes y máximos se guardaron; sin restar calibración ni recortar picos. Valores siguientes en ns:

### Matriz principal

2026-10-19T01:50:26Z a 2026-10-19T01:51:22Z.

| Etapa | Variante | Mediana | p95 | p99 | p99.9 | Máximo |
|---|---|---:|---:|---:|---:|---:|
| wire_verify | baseline | 1,514,384 | 2,296,618 | 3,216,738 | 4,406,228 | 7,443,529 |
| wire_verify | object | 1,412,102 | 2,148,879 | 2,903,812 | 4,269,655 | 5,673,795 |
| wire_verify | optimized | 1,316,339 | 1,925,466 | 2,587,541 | 4,458,006 | 6,178,411 |
| full_ingress | baseline | 1,529,457 | 2,288,306 | 2,929,710 | 4,884,370 | 41,953,113 |
| full_ingress | object | 1,433,373 | 2,178,242 | 2,970,206 | 5,396,382 | 10,164,880 |
| full_ingress | optimized | 1,340,204 | 1,983,282 | 2,619,709 | 4,194,233 | 16,729,030 |

### Confirmación ampliada

2026-10-19T01:52:31Z a 2026-10-19T01:55:14Z.

| Etapa | Variante | Mediana | p95 | p99 | p99.9 | Máximo |
|---|---|---:|---:|---:|---:|---:|
| wire_verify | baseline | 1,551,619 | 2,443,276 | 3,297,798 | 5,290,224 | 16,007,045 |
| wire_verify | optimized | 1,351,762 | 2,097,942 | 2,914,699 | 5,069,205 | 32,779,970 |
| full_ingress | baseline | 1,710,917 | 2,927,257 | 4,243,646 | 6,943,725 | 29,171,219 |
| full_ingress | optimized | 1,495,927 | 2,518,879 | 3,834,467 | 6,409,700 | 74,649,117 |

A sola falló el umbral principal: p99.9 de ingreso +10,48%. A+B cumplió el umbral experimental <=105% del baseline, pero wire p99.9 subió 1,18%; se declaró una confirmación antes de medirla. No se cambió runtime ni umbral para conseguir aprobación.

En la confirmación A+B redujo la mediana de ingreso 12,57%, pero el máximo pasó de **29.171.219 a 74.649.117 ns** (+155,90%). El máximo de verificación pasó de **16.007.045 a 32.779.970 ns** (+104,78%). Hubo **1 descarte de ingreso en optimized**, rep1/pareja4499, frente a 0 en baseline. El presupuesto detectó el resultado tardío y no emitió hechos/candidato aprovechables. La muestra se conserva íntegra en la distribución.

Por tanto, **promoción rechazada**. No se proclama una mejora sin regresiones ni se cambian presupuestos de 50 ms ingreso/5 ms escenario para hacer pasar la muestra. Los máximos observados no son cotas futuras. Las parejas con salidas aceptadas coincidieron; la única pareja descartada no se cuenta como dos salidas iguales.

## Validación

- 51 pruebas Python R6: 11 específicas, 18 R3 con nuevo verificador, 6 diferenciales R5 y 16 defensas heredadas con inyección de R5. Algunas heredadas siguen ejercitando componentes históricos; la integración wire se prueba por separado en las 11 específicas.
- 75 pruebas de regresión R5 sin cambiar sus archivos; 2 Rust R4 + 5 Rust R1; 9 de aislamiento. Verificador de aislamiento correcto, 0 workflows activos y 106 deshabilitados.
- Diferencial de hexadecimal con caracteres inválidos/Unicode/espacios/anchos y límites, y 2.472 variantes de árboles con 4 configuraciones por variante, además de mutaciones y pruebas históricas.
- Comparación del cuerpo semántico y clases de defensa contra R5; las únicas diferencias autorizadas son frontera de parseo e inyección del decoder/verificador. Cuerpos de clases de pruebas trie idénticos a R5.
- SHA256 de biblioteca Rust recompilada: `1cc575699de5a9395dc95b6cc17fbabae0c355459948ba91ef11d204ef0388f4`, igual a R5. Fuentes y manifiestos de R0–R5 verificados intactos.
- No se ejecutaron nuevamente los conjuntos históricos Solidity/EVM no afectados, no se probó un builder, no se autenticó un estado real ni se ejecutó NQC económico. Los datos desconocidos permanecen desconocidos.

## 5 ns y siguiente paso

No hay un nuevo resultado <=5 ns ni se extrapola un filtro preparado a recepción/red/verificación criptográfica. Se conserva la evidencia previa del núcleo mínimo sin cambiar su alcance. La latencia de esta fase no se puede presentar en 5 ns: las llamadas medidas contienen parseo, RLP, hashes y recorridos de pruebas. La matemática Rust permanece sin modificar.

La continuación necesaria es recibir el testigo completo especificado, anclarlo independientemente y ejecutar el importador baseline con sus bytes originales. Después, validar layout/oráculo/IRM/ejecución y medir el recorrido con ese corpus auténtico. Hasta entonces, conservar R5 y la autorización comercial cerrada. Los experimentos A/A+B no son recomendación de sustitución.

## Artefactos

README: reproducción e importación. PRE_REGISTER y CONFIRMATION_PLAN: criterios previos. STABILITY.json: decisión final que prevalece sobre la selección provisional de la primera matriz. evidence/benchmark y evidence/confirmation: tiempos/estados/orden/calibración/metadatos. scripts/verify_results.py y verify_confirmation.py reconstruyen ambas estadísticas. SHA256SUMS cubre cada archivo salvo el propio manifiesto. PROVENANCE registra lo probado, fallado y pendiente.
