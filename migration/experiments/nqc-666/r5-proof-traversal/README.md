# NQC 666 R5 — recorrido único de pruebas de estado

Experimento offline aditivo sobre R4. No altera main ni las fuentes de R0–R4.
La propuesta de 6 cerebros, 6 cazadores y 6 guardianes sigue siendo lógica: R5
optimiza la integridad de datos/estado sin añadir servicios ni agentes.

`python/proof_traversal.py` conserva decodificación RLP estricta, Keccak, validación
de forma y controles de completitud. Reutiliza los objetos decodificados y obtiene
valor y cobertura en un único recorrido de py-trie. `state_evidence_fast.py`
conserva los cuerpos verify/_verify de R3; `fast_gateway.py` conserva Ticket y
StableGateway de R4. Los tests comprueban esas igualdades, además del comportamiento.

La biblioteca Rust R4 y la aritmética R1 se reutilizan sin cambios. No se modifica
el cazador/priorizador R2 ni se elimina la autorización financiera final. Aquí la
puerta comercial permanece cerrada. Los escenarios siguen siendo condicionales:
precio supuesto, sin ejecución de oráculo/IRM, con estado sintético fijado.

## Reproducir

Requisitos ya presentes en el entorno de esta investigación: Linux x86-64,
Rust/Cargo 1.90.0; Python 3.12; trie 4.0.0, rlp 5.0.0, eth-hash 0.8.0,
pycryptodome 3.24.1. No dependencias nuevas ni instalaciones en la reproducción.
Entorno y hashes exactos: `evidence/build-metadata.json` y
`evidence/benchmark/result.json`.

Desde este directorio, con el compilador y el Python correspondiente en PATH:

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/reproduce.py --out /tmp/nqc666-r5-new-run
PYTHONDONTWRITEBYTECODE=1 python scripts/verify_results.py evidence/benchmark
sha256sum -c SHA256SUMS
```

El directorio de salida debe ser nuevo y estar fuera del repositorio. Se compila
R4/R1 sin red, se ejecutan las pruebas Python/Rust y aislamiento, y se miden ambas
variantes en el mismo proceso fijado a una CPU permitida. No requiere claves,
RPC, simulador externo ni configuración de GitHub. Las pruebas no activan CI.

Las mediciones son individuales con CLOCK_MONOTONIC_RAW. `raw.zip` contiene
vectores little-endian u64 de tiempos, calibración e índices; los vectores de
estado contienen un byte por intento (0: salida, 1: descarte por plazo/caducidad).
Los deltas pareados se reconstruyen de los dos vectores. Ningún descarte se
elimina de la distribución. Se conserva orden alternado R4/R5 y semilla por ronda.

El nuevo importador activa este mismo gateway R5 para archivos locales:

```sh
python scripts/import_witness.py --packet packet.json --policy policy.json \
  --library /tmp/nqc666-r5-new-run/target/release/libnqc_666_stable_ingress.so \
  --library-sha256 HASH_DE_BUILD_METADATA --observed-now TIMESTAMP_DE_REPLAY \
  --out /tmp/nqc666-r5-witness-new
```

Conserva bytes y hashes de ambos archivos. El código de salida 0 significa
vinculación a la raíz configurada; 2 registra un rechazo sin hechos parciales.
Ninguno autoriza operar. `--assumed-price` es opcional y siempre condicional.
La política es una configuración independiente, no evidencia de consenso.

Sonda auxiliar de asignaciones, separada de latencia y sin calentamiento:

```sh
python scripts/memory_probe.py --out /tmp/nqc666-r5-memory-new.json
```

El CLI y esta sonda se añadieron después de la matriz; las fuentes del camino
medido no cambiaron. Las pruebas finales incluyen el CLI y ambos verificadores.

## Frontera de confianza

El decodificador es interno: no expone nodos a consumidores del gateway. Su caché
solo dura el paquete; cada prueba requiere su propio mapa. La raíz configurada
no prueba consenso. La vinculación a esa raíz no atestigua layout del runtime ni
vigencia del oráculo. Un hermano inline analizado pero no recorrido sigue siendo
sobrante si aparece como nodo independiente. El acceso está fijado a py-trie 4.0.0;
una actualización exige repetir equivalencia y mediciones.

Conservar cuerpos de código en archivos nuevos permite mantener referencias
históricas inmutables. Esta duplicación es deliberada y queda controlada por
pruebas de igualdad; no es una segunda implementación de la matemática/trie.

Presupuestos R4: 50 ms ingreso, 5 ms escenario. Rechazan resultados tardíos;
no interrumpen una pausa del host. No hay cota de tiempo real, inclusión Ethereum
ni autorización para operar. `REPORT.md` distingue lo demostrado y lo pendiente.
