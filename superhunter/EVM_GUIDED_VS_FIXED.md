# SUPERHUNTER — comparación EVM con presupuesto idéntico

Esta unidad responde a una pregunta acotada: **¿cambia la cobertura observable de
nuestros contratos propios cuando elegimos el padre de mutación usando la traza
anterior, en lugar de mutar siempre la secuencia inicial?**

## Qué se ejecuta

`compare-owned-evm` realiza dos experimentos, cada uno con una secuencia inicial
y `--candidates` mutaciones (1–3). Los dos usan:

- Exactamente los mismos controles propios `conservation` y `delayed_credit`.
- Los mismos dos perfiles de compilación, `solc 0.8.30` y Geth EVM 1.17.10
  fijados por hash.
- La misma secuencia inicial de cuatro operaciones, el mismo seed y las mismas
  recetas de mutación por iteración.
- La misma cantidad de secuencias y llamadas EVM, incluidos los constructores.
- Traces nativos con PCs e información conservadora de `JUMPI`; cada llamada
  se contrasta con dos oráculos de estado/retorno y conciliación de unidades.

**Brazo guiado:** ejecuta cada secuencia, observa los nuevos rasgos PC/arista
y selecciona el próximo padre por novedad/rareza. **Brazo sin feedback:**
aplica la misma receta a la secuencia *inicial* en cada iteración. No consume
trazas para seleccionar padres. Esto aísla una diferencia de selección; **no es
comparación contra un fuzzer aleatorio completo ni contra Slither/Echidna**.

El reporte cuenta rasgos observados por control y perfil, así como reversiones,
operaciones aplicadas y presupuesto idéntico. El verificador rechaza programas,
semillas o presupuestos alterados y vuelve a ejecutar ambos brazos desde sus
fuentes fijas. El paquete debe guardarse privado.

## Comandos

```bash
SRC=$(python3 - <<'PY'
from superhunter import quality
from superhunter.safe_io import canonical
import hashlib
print(hashlib.sha256(canonical(quality.source_snapshot())).hexdigest())
PY
)
python3 -m superhunter compare-owned-evm \
  --solc /ruta/solc-fijado --evm /ruta/evm-fijado \
  --expected-source "$SRC" --seed 20261105 --candidates 2 \
  --out /privado/comparacion-nueva
python3 -m superhunter verify-owned-evm-comparison \
  --solc /ruta/solc-fijado --evm /ruta/evm-fijado \
  --expected-source "$SRC" --expected-seed 20261105 \
  --expected-candidates 2 --bundle /privado/comparacion-nueva
```

La huella de fuentes, seed y presupuesto son referencias externas. Los hashes
internos establecen consistencia y el replay comprueba reproducibilidad,
**no autenticidad de un productor remoto**.

## Límites de interpretación

- Una diferencia positiva de rasgos **no demuestra** mayor tasa de hallazgos,
  precisión, recall ni superioridad estadística. Un resultado negativo también
  se reporta sin ocultarlo.
- Los rasgos son PCs y saltos condicionales observados en las llamadas
  instrumentadas: no todos los caminos posibles ni cobertura semántica global.
- `JUMPI` cuyo destino es la instrucción siguiente puede ser indeterminado;
  no se inventa una rama tomada.
- Un solo seed, dos contratos aritméticos conocidos y pocas mutaciones no
  constituyen un benchmark representativo; no hay programas de terceros.
- Se ejecuta el mismo compilador y la misma EVM en ambos brazos, con recaptura
  de estado. Los oráculos aritméticos no son una segunda EVM.
- No hay RPC, envíos, explotación, tokens, fondos, monitoreo 24/7 ni hallazgos
  de vulnerabilidades originales. No se amplía automáticamente el alcance de
  los catálogos 27/50/25.

## Recibos QA por encima de 1,800 pruebas

La agregación histórica de ocho workers duplicaba el inventario global y las
huellas de fuentes en cada recibo, acercándose al límite de 2 MB del artefacto.
Ahora `quality.run_check` conserva **todos los tests individuales**, el inventario
global y ocho registros compactos: cada uno omite solamente los tres campos
idénticos al exterior (`sources_before`, `sources_after`, `global_discovered`).
Registra además el SHA-256 de la forma original completa de cada worker.

Durante `verify-check`, esos campos se reconstruyen y se comprueban **los ocho
SHA-256 antes de volver a evaluar** contadores, cobertura, identidad y resultados.
El formato anterior, sin compactación, sigue siendo verificable. El límite global
`safe_io.MAX_BYTES` no cambió. Los controles negativos demuestran que recalcular
el manifiesto tras alterar una prueba no hace que su registro de worker sea válido.
La compactación no es cifrado, una firma de identidad ni certificación del productor.
