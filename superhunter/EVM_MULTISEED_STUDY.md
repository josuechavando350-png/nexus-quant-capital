# SUPERHUNTER — estudio pareado multisemilla sobre EVM propia

Esta unidad implementa un **estudio local**, no descubrimiento autónomo ni auditoría
externa. No realiza solicitudes de red, llamadas RPC, envíos de transacciones,
expedientes de bounty ni ejecución de fuentes de terceros. Se limita a dos
contratos aritméticos propios y dos configuraciones fijadas de `solc 0.8.30`.

## Limitación corregida

El plan anterior `next_mutation` solo utilizaba la paridad de la semilla durante
la segunda mutación; muchas semillas equivalían a exactamente el mismo programa.
El nuevo plan utiliza el entero uint64 completo para ordenar mediante SHA-256
los **ocho pares** (4 pasos × cantidad/gas), sin reemplazo. Se eligen 2–3 mutaciones
distintas por semilla. Se conserva el módulo anterior intacto para comparación
histórica. El registro muestra cuántos planes de mutación **distintos** hubo; no
confunde número de semillas con diversidad de programas.

## Dos brazos bajo el mismo presupuesto

- Guiado: toma el padre seleccionado por novedad y rareza a partir de trazas
  efectivamente observadas en las ejecuciones previas del mismo brazo.
- Sin feedback: aplica cada mismo operador directamente a la secuencia inicial.
- Ambos ejecutan los mismos controles, compiladores, perfiles, cantidad de
  secuencias y llamadas. La secuencia inicial se ejecuta independientemente
  para cada brazo y semilla.
- Cada instrucción de mutación es un flip reversible (cantidad 0↔16 o gas
  normal↔1); la planificación se fija ANTES de observar resultados. Evita
  deduplicaciones silenciosas y preserva un presupuesto verificable.
- Cada llamada se ejecuta realmente con la EVM fijada y se contrasta con el
  modelo de estado/retorno y la conciliación contable existentes.

Ejemplo con dos semillas predefinidas y dos mutaciones por semilla:

```bash
SRC=$(python3 - <<'PY'
from superhunter import quality
from superhunter.safe_io import canonical
import hashlib
print(hashlib.sha256(canonical(quality.source_snapshot())).hexdigest())
PY
)
python3 -m superhunter study-owned-evm \
  --solc /ruta/al/solc-fijado --evm /ruta/al/evm-fijado \
  --expected-source "$SRC" --seeds 20261105,20261106 --mutations 2 \
  --out /privado/estudio-nuevo
python3 -m superhunter verify-owned-evm-study \
  --solc /ruta/al/solc-fijado --evm /ruta/al/evm-fijado \
  --expected-source "$SRC" --seeds 20261105,20261106 --mutations 2 \
  --bundle /privado/estudio-nuevo
```

El comando de verificación requiere fuente, semillas y presupuesto **externos**
al paquete, regenera todas las observaciones con los binarios fijados, recalcula
los resultados y el AuditLog original de DIABLO y rechaza cambios del artefacto.
La carpeta del expediente es privada y no se sobrescribe.

## Interpretación rigurosa

Una semilla NO constituye una muestra independiente de protocolos; todas las
semillas aquí comparten **los mismos dos contratos conocidos** y la misma
función de selección de mutaciones. Los rasgos PC/arista no son cobertura de
rutas total ni una medida de detección de fallos. El número de rasgos puede
cambiar por perfil de compilación; esa identidad forma parte de cada rasgo.

Incluso si un brazo obtiene más rasgos, **no se declara significación
estadística, mejor recall, bugs encontrados ni vulnerabilidades confirmadas**.
Antes de afirmar superioridad se necesitan múltiples sistemas no vistos, casos
ciego/prerregistrados, tiempos/costos comparables y reproducción independiente.

Limitación del experimento: solo dos operadores de flip, ocho posiciones de
mutación en cuatro pasos, 2–4 semillas y 2–3 mutaciones; no es un fuzzer de
propósito general. No sustituye Echidna, Medusa, Foundry ni auditoría humana.
