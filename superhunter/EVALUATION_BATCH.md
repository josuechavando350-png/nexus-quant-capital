# Evaluación de respuestas sobre los campos del encabezado NQC

Cinco componentes reciben observaciones nuevas en los mismos ocho grupos de 96 entradas publicados en el [protocolo de representación](product_supply/review-115-holdout.json). Se regeneran tanto las entradas como las etiquetas desde las semillas. Para cada grupo un proceso aislado recibe únicamente encabezados y ejecuta el clasificador revisado. El verificador comprueba los hashes de entrada, etiquetas y predicciones contra el protocolo. Cada evaluador trabaja sobre las predicciones nuevas y cuatro modificaciones controladas. Las pruebas comparan también con oráculos de exactitud y de conteo independientes.

| Componente usado | Qué comprueba | Un resultado observado |
|---|---|---|
| Promptfoo `handleEquals` | Compara objetos JSON tipados con las listas exactas de campos incorrectos. También rechaza JSON incompleto. | 768/768 originales. Al omitir la comprobación de `extraData` identifica los 73 errores y acepta 695. |
| Langfuse, estadísticas de categorías | Compara categorías de referencia y de respuesta mediante kappa de Cohen, acuerdo y F1 ponderado. | Kappa cae de 1 a 0.855 al retirar `extraData`. El acuerdo baja a 0.905 y el F1 ponderado a 0.862. |
| Ragas `fbeta_score` | Mide precisión/recobrado por campo con tres ponderaciones. | Al omitir `extraData`, su F1 cae a cero; las otras cuatro clases quedan en uno. Al confundir parcialmente `gasUsed` con `hash`, el F2 de `gasUsed` baja a 0.548 y el F0.5 de `hash` a 0.501. |
| smolagents, evaluador GAIA | Contrasta la normalización prevista para respuestas de lenguaje natural con los identificadores exactos, que distinguen mayúsculas y puntuación. | Acepta 384 identificadores alterados en cada uno de los controles de capitalización y puntuación. El consumidor conserva estas discrepancias. |
| Transformers, normalizador Whisper | Examina si una comparación relajada conserva la identidad de los campos de datos. | Acepta 384 respuestas falsas en el control de capitalización. En el control de puntuación detecta los 384 cambios. |

Los dos normalizadores ayudan a identificar calificaciones engañosas para respuestas estructuradas. El resultado estricto de la consulta conserva la distinción de campos originales. El alcance es la representación de datos. No se entrenan modelos ni se envían peticiones a proveedores. El [expediente](product_supply/evaluation-batch-receipt.json) mantiene huellas de las cinco matrices de casos, de las fuentes y de los conjuntos de errores.

**Reproducción**. En Linux, especificar `NQC_TRUST_TEST_SOURCES` con la ruta `upstream` de los checkouts y `NQC_EVALUATION_WHEEL` con el wheel `regex` de los entornos DSPy o Inspect previamente revisados. El worker comprueba el SHA-256 `8a966a5afe94ed9fb06deeecd9e3e51c3a5ab7d920e13f8128338e3fcdfed2b0`. Usar Python 3.12, Node 24 con soporte nativo de TypeScript, `prlimit`, namespaces de red/usuario y Git.

```sh
python3.12 -B -m unittest -v superhunter.tests.test_product_evaluation_batch
```

El lote añade controladores de NQC y resultados. Lee el código upstream desde las revisiones fijadas en los submódulos. El archivo de estadísticas de Langfuse procede de `web/src/features/score-analytics/lib`, fuera de sus directorios `ee`; el módulo Whisper contiene el aviso de OpenAI y Hugging Face. Los textos de licencia y avisos permanecen en los checkouts. No se distribuyen los ejecutables, el wheel ni los módulos upstream en este lote.
