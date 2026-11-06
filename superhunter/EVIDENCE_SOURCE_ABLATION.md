# SUPERHUNTER — Resiliencia de evidencia, experimento contrafactual offline

**Estado:** incremento funcional acotado de M1, no una detección de vulnerabilidades. Depende de la auditoría de caminos dirigidos (#51), el triaje de cadenas (#50) y de sus fuentes forenses/EVM privadas. **No cambia los bytes originales**.

## Funciones implementadas

- Verifica primero el `path-audit` anterior, su `triage` y las fuentes originales a través de los verificadores correspondientes (forense/journals/replay EVM); no acepta un manifiesto aislado como prueba.
- Para cada cadena valida y enumera las observaciones y relaciones **declaradas**, extrae los IDs de fuentes localmente verificadas y calcula exactamente el subconjunto mínimo que cubre cada obligación de evidencia (máximo 8 fuentes). Soluciones equivalentes se desempatan lexicográficamente; una obligación sin respaldo produce `null` en vez de un `PASS`.
- Recalcula el **triaje real** ocho veces como máximo, retirando virtualmente cada identidad de fuente de todas las referencias, sin tocar los archivos originales. Expone el aumento de brechas y cambios de prioridad en cada candidato; no inventa probabilidades.
- Emite paquete privado con recibo verificable; otro proceso vuelve a abrir las fuentes y reconstruye el mismo análisis. Detecta reportes alterados aun cuando se vuelva a sellar su `COMPLETE.json`.

## Límites epistemológicos

Un ID de fuente no equivale a un productor autenticado ni a un sensor estadísticamente independiente. Dos IDs podrían provenir de un mismo dispositivo, una sola persona o los mismos datos. La cobertura exacta es una propiedad del **grafo de evidencias declarado**, NO prueba causal, de explotabilidad, prioridad CVSS, permiso de testeo ni gravedad crítica. Incluso si el resultado no cambia después de remover una fuente, eso NO acredita redundancia real frente a un adversario que controla ambas fuentes.

El resultado de las pruebas usa incidentes y datos **sintéticos/propios** de laboratorio. No se ejecuta Geth real, RPC, escáner ni explotación; no se envían reportes a programas de terceros.

## Comandos

```sh
python3 -m superhunter audit-source-ablation \
  --path-audit /privado/ruta-auditoria \
  --triage /privado/triage-original --sources /privado/sources-originales.json \
  --out /privado/resultado-nuevo

python3 -m superhunter verify-source-ablation \
  --bundle /privado/resultado-nuevo \
  --path-audit /privado/ruta-auditoria \
  --triage /privado/triage-original --sources /privado/sources-originales.json
```

El directorio de salida debe ser nuevo y privado. No se permite sobrescribirlo. Nunca subir bundles que contengan nombres, eventos o rutas originales.

## Criterio de aceptación

- Revalidación de origen y de recibo independiente, positivos, negativos, rediseño del `COMPLETE.json` y ausencia de fuga en stdout.
- Casos de cobertura de 1 y de 2 fuentes, obligación ausente, revocación virtual con diferencias de priorización.
- Verificación de 500 instancias sintéticas contra oráculo independiente por enumeración de máscaras.
- Suite completa de SuperHunter sin omisiones ni aumento de límites y tests previos intactos.
- Pendiente: autenticación real de fuentes, intervención causal reproducible en laboratorio, ejecución nativa EVM independiente, NQC y aislamiento global.
