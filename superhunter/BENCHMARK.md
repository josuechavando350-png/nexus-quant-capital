# Evaluación reproducible por caso — alcance y medición

Este módulo puntúa resultados etiquetados y ejecuta un control fijo sobre el
analizador de permisos existente. Avance parcial del motor 10, Benchmark &
Operations, propuesto en la conversación. No descubre vulnerabilidades, no
planifica ataques ni ejecuta código aportado por terceros. No se ha medido todavía
la efectividad del Hunter sobre un corpus independiente de vulnerabilidades.

## Dos recorridos diferentes

1. `evaluate-benchmark`: puntúa un corpus y resultados suministrados. No ejecuta
   el productor ni autentica sus afirmaciones. Los archivos de entrada se conservan.
2. `benchmark-permissions`: llama realmente a `permissions.analyze_policy` sobre
   ocho modelos RBAC propios y fijos; `verify-permission-benchmark` vuelve a ejecutar
   el analizador contra esos mismos modelos. No admite motor, objetivo o payload
   proporcionado por el usuario. Las etiquetas se declaran antes de esas llamadas.

El segundo recorrido es una regresión de modelos conocidos, no un benchmark ciego.
Cada caso pregunta si la conjunción de propiedades explícitas de su política se
incumple. Cuatro casos incumplen y cuatro satisfacen sus propiedades. La etiqueta
`medium` en estos ejemplos es ilustrativa: no es severidad de un bug bounty.

## Integración

`CLI -> corpus/resultados -> dos contadores independientes -> métricas -> AuditLog
original DIABLO -> paquete privado -> verificador`. El paquete es compatible con
la firma de custodia existente sin cambiar ni copiar claves privadas.

El control fijo es obligatorio en `review-platform` bajo `benchmark_control/`.
La revisión conserva hashes de sus seis archivos, reejecuta sus comprobaciones
al verificar y muestra su alcance en el informe. Una etapa ausente o alterada
impide aprobar la revisión conjunta. El control central QA registra el componente,
sus dependencias y las pruebas obligatorias.

## Comandos

```bash
python3 -m superhunter benchmark-permissions --out /privado/control-nuevo
python3 -m superhunter verify-permission-benchmark --bundle /privado/control-nuevo

python3 -m superhunter evaluate-benchmark \
  --corpus /privado/corpus.json --run /privado/run.json --out /privado/metricas-nuevas
python3 -m superhunter verify-benchmark \
  --bundle /privado/metricas-nuevas --expected-corpus-sha256 HASH_CONSERVADO_APARTE

python3 -m superhunter review-platform --out /privado/revision-nueva
python3 -m superhunter verify-platform --bundle /privado/revision-nueva
```

El hash esperado identifica el JSON canónico del corpus, no sus espacios o saltos
de línea. Conservarlo fuera del paquete. El verificador lo exige para evitar que
una sustitución del corpus se justifique con sus propios hashes. No acredita por
sí mismo quién eligió las etiquetas o si son correctas. La custodia del paquete
completo es una comprobación separada contra claves de confianza independientes.

## Reglas de evaluación

La unidad es un caso con UNA condición booleana revisada (puede ser la conjunción
de varias aserciones). Los resultados son `positive`, `negative`, `abstain` o
`error`. No se puntúan múltiples alertas como si fueran múltiples casos. Todos los
IDs del split seleccionado deben aparecer exactamente una vez. Una omisión es
error del corpus de resultados; no se convierte en ausencia de vulnerabilidades.

Se calculan TP, FP, TN y FN para las decisiones positivas y negativas. Se
conservan separadamente abstenciones y errores tanto en positivos como negativos.

- Precisión = TP / (TP + FP).
- Recall sobre TODOS los positivos = TP / positivos etiquetados, incluyendo
  abstenciones y errores en el denominador. Es la medida principal de cobertura.
- Recall solo entre casos decididos = TP / (TP + FN), rotulado como condicional.
- Cobertura de decisiones = (TP + FP + TN + FN) / todos los casos seleccionados.
- FPR entre negativos decididos = FP / (FP + TN), también explícitamente condicional.

Cada cociente conserva numerador, denominador y valor. Un denominador cero produce
`null`, nunca 100% por defecto. No se afirma precisión por severidad real: las
falsas alarmas no tienen una severidad verdadera. Se muestra recall por severidad
de la etiqueta y matrices por familia, conservando el soporte de cada grupo.

Costos: unidades enteras de micro-USD declaradas. Si falta un costo, el total es
`null` y se conserva un subtotal conocido. El costo por TP también es desconocido
cuando faltan costos o no hay TP. La suma de tiempos por caso no es tiempo de
pared ni medición de paralelismo. En el control fijo se mide duración por llamada,
pero no se inventan costos de infraestructura.

## Separación y límites del corpus

El manifiesto incluye todos los casos declarados de train, development y test.
Se rechaza contenido con hash repetido para evitar duplicación de soporte y
contaminación directa. Un `group_id` no puede atravesar splits. Dentro de un split,
las variantes de una misma familia pueden compartir grupo. Estos controles NO
revelan datos de entrenamiento no declarados, memorización del modelo, similitud
semántica desconocida ni exposición previa al conjunto: siempre
`blind_evaluation_established=false` y `generalization_established=false`.

Los hashes de contenido son metadatos aportados, no una descarga/autenticación de
fuentes. Los controles fijos sí recalculan los hashes de sus políticas incluidas.
Máximo 4.000 casos y los límites de archivos del IO existente. Los esquemas
rechazan campos adicionales, IDs repetidos, tipos incorrectos y números no finitos.

## Significado de aprobación

`LABELED_CASE_EVALUATION` significa que la puntuación del corpus se calculó y sus
dos contadores coincidieron. No es una etiqueta de calidad ni prueba de ejecución
del productor. Exit 0 significa cálculo/verificación completados, incluso con
métricas malas. `FIXED_PERMISSION_EVALUATION_REPLAYED` solo acredita la repetición
de los ocho controles definidos. Un resultado favorable no completa las 50
capacidades ni convierte una política mal configurada en un fallo de terceros.

Los originales y la auditoría siguen siendo privados. El resumen no imprime nombres
de corpus, IDs de casos, textos ni fuentes del productor. No se implementan
aprendizaje autónomo, envío de reportes, conectores, análisis EVM ni escaneo.

## Fuentes metodológicas

Documentación primaria consultada el 4 de noviembre de 2026 (no se distribuye ni
se requiere scikit-learn para ejecutar este módulo):
- Métricas: https://scikit-learn.org/stable/modules/model_evaluation.html
- Contaminación de evaluación: https://scikit-learn.org/stable/common_pitfalls.html

La contabilidad de abstenciones es una convención explícita de este evaluador;
no se atribuye a un estándar de clasificación de vulnerabilidades ni a una
plataforma de recompensas. No se reportan intervalos estadísticos o probabilidades
de hallar un bug en producción a partir de estos controles diseñados.
