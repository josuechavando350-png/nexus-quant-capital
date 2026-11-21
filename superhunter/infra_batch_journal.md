# Correlación de dos journals de NQC

SUPERHUNTER conserva los cuatro eventos normalizados de su fixture histórico de dos fuentes. La prueba reproduce la preparación del fixture original de [correlación](tests/test_journal_correlation.py) y compara exactamente la proyección publicada con su salida. Cada fuente empieza su secuencia en cero. Usar la secuencia sin la fuente colapsaría cuatro eventos en dos. El consumidor mantiene la pareja fuente/secuencia y rechaza el control que atribuye eventos de dos fuentes al mismo origen.

| Proyecto | Aporte verificado |
|---|---|
| Jaeger (#48) | Su código Go convierte cada instante a nanosegundos Unix y de vuelta a UTC. Los controles confirman que el instante cero y una fecha previa a la época producen el mismo valor centinela. Esa salida no se usa para ordenar evidencia. |
| Hubble (#89) | El paquete de tiempo distribuido con la CLI lee los cuatro tiempos de journal y sus cuatro representaciones equivalentes. Rechaza una fecha inválida. Una diferencia de 1 ns se conserva en el formato de nanosegundos y desaparece en la vista de milisegundos. |
| Falco (#86) | NQC consume el formato de segundos UTC y nueve dígitos fraccionarios del serializador de eventos JSON. El adaptador aplica las unidades y la precisión extraídas del código a las marcas del journal. Hubble y Jaeger reproducen sus cuatro instantes exactos. |

Las tres capacidades comparten datos con el analizador forense existente. El fixture es una prueba de regresión propia. No contiene observaciones de equipos reales, alertas de Falco ni atribución causal. Se omiten mensajes y cursores de los journals; se conservan las identidades normalizadas y sus hashes.

## Reproducir

Se reutiliza la distribución de Go 1.27.4 para Linux amd64 configurada mediante `NQC_STATE_GO`. El compilador debe tener SHA-256 `de0ae3e082ce7599eae4fb69fa2ef1e43b8f31ffd3fce62cdf81930aa9005050`. La compilación sólo utiliza la biblioteca estándar, los dos archivos originales de Hubble y Jaeger y el controlador del producto. Dos builds en directorios y cachés distintos produjeron el binario `673d1d0fea66e0e4be03867810b2c46c699c1df2d099711d29ffe03d3c8a0f39`. Para evitar recompilar, `NQC_TIMELINE_RUNNER` admite un binario previo que se autentica antes de cada ejecución. No se requiere conectividad.

```sh
python3.12 -B -m unittest superhunter.tests.test_infra_batch_journal
python3.12 -B - <<'PY'
from pathlib import Path
from superhunter.product_timeline_formats import review
from superhunter.product_review import sha
from superhunter.safe_io import canonical

result = canonical(review(Path('upstream')))
assert result == Path('superhunter/product_supply/infra_batch_journal_observed.json').read_bytes()
print(sha(result))
PY
```

SHA-256 de las tres observaciones: `94c506cbbd7a988a8d1934938ff6b16de6ae16d292a7bd586fdc8497eeb7a0db`. [Fixture normalizado](product_supply/infra_batch_journal_fixture.json) · [Resultados por proyecto](product_supply/infra_batch_journal_observed.json).
