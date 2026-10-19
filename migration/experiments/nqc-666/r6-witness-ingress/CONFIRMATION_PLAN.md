# Confirmación tras la matriz principal, sin cambiar el runtime

La primera matriz cumple el umbral predefinido para A+B frente a baseline, pero
wire_verify p99.9 aumenta 1,18%. A sola falla p99.9 de ingreso (+10,48%).
Además, el máximo A+B es peor que A sola, aunque mejor que baseline. No se
declara ausencia de regresiones ni se promueve por defecto ninguna alternativa.

Resolver la incertidumbre de colas justifica una única confirmación más amplia:
3 repeticiones × 8192 parejas × 2 variantes (baseline y optimized) × 2 modos.
98.304 ventanas individuales; mismo corpus, 13 precios, CLOCK_MONOTONIC_RAW,
afinidad/GC/defensas/plazos; primera variante alternada y nueva semilla fija.
No cambia ningún archivo Python de la matriz original. Conservación de ambas
matrices y sus máximos; no agruparlas para esconder una regresión.

Pregunta concreta: ¿se repite la mejora de mediana y se sostienen p99, p99.9 y
máximo frente al mismo baseline? Para hablar de mejora de todas las métricas en
esta confirmación, mediana >=5% menor por repetición/modo y p95/p99/p99.9/máximo
agregados <=baseline, con descartes no mayores. Si no, queda experimental sin
recomendación de sustituir R5. Un pase tampoco autentica estado ni prueba una
cota temporal del host; el resultado de la primera matriz permanece visible.
