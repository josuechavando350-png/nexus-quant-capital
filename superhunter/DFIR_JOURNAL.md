# DFIR journal JSONL — recuperación y análisis acotados

Entrega de **ingesta auténtica de bytes** desde una exportación existente de `journalctl -o json`, completamente *offline*. Es un parser propio que produce eventos normalizados y enlaza cada evento al fragmento exacto de su archivo original mediante offset, longitud y SHA-256. No se limita a inventariar herramientas ni a generar ejemplos sintéticos: el motor recibe una entrada real (archivos que ya existan), la analiza y el verificador la reproduce independientemente. Los tests utilizan entradas de laboratorio sintéticas etiquetadas; **no se ha investigado un incidente auténtico de producción**.

## Contrato

- `journal.jsonl`: un JSON por línea, hasta 512 líneas y 2 MB por archivo, sin saltos CR. Campo obligatorio `__REALTIME_TIMESTAMP` como microsegundos UNIX decimales, preservado con exactitud de microsegundos sin floats. Cursor opcional: si se declara, se rechazan duplicaciones.
- `metadata.json`: identidad `source_id` aportada por operador y cota `clock_uncertainty_ms`, máxima 24 horas; no constituye identidad de productor autenticada.
- `normalized.json`: perfil `normalized-evidence-timeline-v1` común al análisis forense anterior. Cada fila original produce un evento `application` (NO significa creación de proceso ni acción maliciosa), su SHA-256 exacto y orden de aparición.
- `timeline.json`: comparación de tiempos con incertidumbre, detectando inversiones, intervalos superpuestos y límites del análisis. La prioridad de clasificación de contradicción no es prueba de una intrusión.
- `receipt.json`: identidad exacta de fuentes Python, el SHA-256 de la exportación, offsets/longitudes/hashes de cada línea y vínculos al modelo y análisis.
- `REVIEW.md`: resumen deliberadamente **sin texto `MESSAGE`** ni otros campos sensibles. El archivo original y sus potenciales datos personales solo se guardan en la salida privada.

Se preserva todo el original byte por byte en una carpeta privada 0700. El marcador `COMPLETE.json` se escribe al final. No se sobrescriben salidas. Un verificador distinto recarga el archivo original y reconstruye desde cero ambos modelos; falsificar un reporte o rehash local sin conciliar datos produce rechazo.

## CLI

```bash
python3 -m superhunter ingest-journal \
  --input /privado/journal.jsonl --source-id host-lab \
  --clock-uncertainty-ms 2000 --out /privado/journal-evidence-001
python3 -m superhunter verify-journal --bundle /privado/journal-evidence-001
```

## Límites honestos y siguiente paso

Esta entrega no contacta objetivos, no extrae el journal por SSH, no analiza archivos binarios ni imágenes de RAM/disco, no verifica firmas ni cadenas de custodia externas, no detecta de forma autónoma intrusiones y no acredita causalidad de eventos. En otras palabras: **no completa DFIR ni M1**.

Siguiente unidad técnica: unir las evidencias verificadas de `ingest-journal` con otras fuentes (trazas EVM o eventos de auditoría de laboratorio), formular hipótesis refutables y verificar las dependencias y los resultados experimentalmente. Mantener este flujo totalmente autónomo respecto de NQC histórico y SuperHunter-GUARDIAN independiente.
