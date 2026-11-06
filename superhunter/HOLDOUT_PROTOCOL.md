# SUPERHUNTER — compromiso, congelación y revelación de etiquetas

Unidad defensiva **offline** y original de control de un benchmark. No ejecuta
modelos, contratos, Slither, `solc`, Geth, redes o programas de bug bounty.
No acredita una evaluación ciega real: para eso un custodio externo debe crear y
mantener las etiquetas en secreto, fijar temporalmente los compromisos y evitar
filtraciones en nombres de casos, fuentes, dependencias, historias y conversaciones.
Las funciones aquí solo comprueban la integridad y coherencia de un procedimiento.

## Contratos reales y orden

1. **Prepare (`prepare-holdout`)**: el custodio prepara un `manifest.json` de
   casos SIN etiquetas y un `labels.json` privado. La herramienta genera un nonce
   con `secrets.token_hex(32)` y guarda los datos privados en una carpeta 0700;
   publica únicamente un manifiesto sin verdades y un SHA-256 con separación de dominio.
   Conservar **por fuera** el hash de `COMPLETE.json` del directorio público.
2. **Freeze (`freeze-holdout`)**: el detector recibe **solo** el directorio público,
   produce un `predictions.json` con una decisión por cada caso del split `test`,
   incluidas abstenciones/errores. El comando exige el hash público externo, valida
   las identidades y genera un paquete sin etiquetas. Conservar **por fuera** el
   hash `submission_sha256` de su `COMPLETE.json` antes de revelar las etiquetas.
3. **Reveal (`score-holdout`)**: solo con las dos anclas externas y los originales
   privados calcula el puntaje con el motor existente `benchmark.evaluate`. Devuelve
   TP/FP/TN/FN, abstenciones, errores, precisión y recall. Ni el costo declarado ni
   los tiempos se convierten en mediciones autenticadas.
4. **Replay (`verify-holdout`)**: exige ambas anclas de fuera del paquete, rehace
   la unión de etiquetas, reconstruye los contadores y verifica los eventos de
   `AuditLog` de DIABLO y los hashes de código actual.

Ejemplo:

```bash
python3 -m superhunter prepare-holdout \
  --manifest /privado/inputs/manifest.json --labels /privado/inputs/labels.json \
  --public-out /privado/publico-nuevo --private-out /privado/etiquetas-nuevo

python3 -m superhunter freeze-holdout \
  --public /privado/publico-nuevo --predictions /privado/inputs/predictions.json \
  --expected-prepared-sha256 SHA256_PUBLICO_PREVIAMENTE_GUARDADO \
  --out /privado/congelado-nuevo

python3 -m superhunter score-holdout \
  --frozen /privado/congelado-nuevo --private /privado/etiquetas-nuevo \
  --expected-prepared-sha256 SHA256_PUBLICO_PREVIAMENTE_GUARDADO \
  --expected-frozen-sha256 SHA256_CONGELADO_PREVIAMENTE_GUARDADO \
  --out /privado/puntaje-nuevo

python3 -m superhunter verify-holdout \
  --bundle /privado/puntaje-nuevo \
  --expected-prepared-sha256 SHA256_PUBLICO_PREVIAMENTE_GUARDADO \
  --expected-frozen-sha256 SHA256_CONGELADO_PREVIAMENTE_GUARDADO
```

### Formatos

`manifest.json`: `schema_version=1`, `corpus_id`, `provenance` (synthetic o
curated), `cases` con `{case_id, group_id, content_sha256, split, family}`.
Nunca incluye verdad o severidad. Perfiles soportados: solo `train`,
`development`, `test`, y la puntuación usa `test`. Límite actual: 512 casos.

`labels.json`: `schema_version=1`, `corpus_id`, `cases` con
`{case_id, truth, severity}`, exactamente un caso por identidad; positivo exige
severidad low/medium/high/critical, negativo exige none. El nonce se genera en
la etapa pública/privada y nunca entra al paquete de predicciones.

`predictions.json`: `schema_version=1`, `run_id`, `producer` con `name` y
`source_sha256`, `manifest_sha256`, `records` con
`{case_id, decision, elapsed_ms, cost_micro_usd}`. El costo es un entero
no negativo o null (desconocido); el tiempo es declarado, no observado aquí.
Decisiones: `positive`, `negative`, `abstain`, `error`.

## Seguridad y límites verificados

- Rechaza etiquetas modificadas, resultados modificados después de congelar,
  falsos conteos después de revelar, anclas externas incompatibles, resultados
  omitidos, duplicados, IDs de otro corpus, salidas incompletas, rutas simbólicas,
  archivos adicionales y cambios de código.
- Rechaza un mismo contenido SHA-256 repetido y grupos relacionados repartidos
  entre train/development/test, pero esto no detecta **todas** las fugas semánticas.
- Los hashes protegen consistencia de los bytes **solo si** las anclas quedan en
  custodia independiente, antes de observar predicciones y etiquetas.
- Un desarrollador con acceso al repositorio del contrato puede conocer sus
  mutaciones deliberadas. Ninguna de las pruebas sintéticas demuestra ceguera;
  `blind_evaluation_established=false` se mantiene en los resultados.
- La fuente/procedencia de etiquetas, el productor, los costos y el orden
  temporal NO se autentican mediante el protocolo. Un adversario que controla
  tanto los datos como ambas anclas puede fabricar un experimento coherente.
- Se requiere benchmark externo de programas propios/autorizados, aislamiento
  operativo y revisión independiente antes de alegar precisión general.
- Los paquetes de puntaje contienen **etiquetas privadas**: no subirlos a GitHub
  ni compartirlos en reportes públicos. El resumen omite IDs y datos originales.

Esta unidad no cambia los catálogos originales de 27/50/25 y no cuenta como
una vulnerabilidad nueva ni mejora demostrada de la detección.
