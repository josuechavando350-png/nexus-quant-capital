# NQC666 R2 — presión de eventos y recuperación determinista

Experimento local aislado en Rust sobre R1. No autoriza operaciones comerciales.

- [Diseño, prueba de equivalencia y límites](DESIGN.md)
- [Hipótesis, piloto rechazado y enmienda previa a la matriz final](PRE_REGISTER.md)
- [Procedencia de fuentes](PROVENANCE.json)
- [Informe de resultados](REPORT.md)
- [Todas las distribuciones y repeticiones](RESULTS.md)
- [Manifiesto SHA-256](MANIFEST.sha256)

## Verificar lo entregado

Requiere Rust 1.90.0 y Python 3.12 instalados; no hay dependencias Rust externas.
Desde este directorio:

```sh
sha256sum -c MANIFEST.sha256
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify.py
CARGO_TARGET_DIR=/tmp/nqc666-r2-check cargo test --locked --offline
```

El verificador recalcula cada percentil desde las muestras crudas, comprueba
checksums equivalentes de variantes y hashes de fuentes/dependencias. El piloto
rechazado se verifica contra su snapshot de fuentes histórico; la matriz final
debe coincidir además con el código actualmente entregado.

## Repetir desde cero

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/reproduce.py --out /tmp/nqc666-r2-run
```

El directorio de salida debe ser nuevo y estar fuera del repositorio. El script
ejecuta formato, Clippy, pruebas Rust, aislamiento, compilación y las 144 corridas
intercaladas. Guarda controles de reloj, metadata, binario compilado, fuentes,
desensamblado, muestras y resultados. No descarga paquetes ni consulta servicios.
La evidencia entregada incluye hash y desensamblado del binario; el ejecutable se
obtiene al compilar. Otra ruta de compilación o versión del toolchain puede cambiar
su hash. Las latencias pueden variar con la máquina y su carga; no se exige obtener
exactamente los mismos nanosegundos para reproducir el procedimiento.

`--pilot` aplicado al código actual produce una medición abreviada **del código
actual**; no reproduce el piloto rechazado de umbral 16. Su versión exacta está
en `evidence/pilot/source.zip`, junto a hashes de las dependencias originales.

El uso directo de una variante de investigación es explícito:

```rust
// Parámetros: BULK, SINGLE_WRITE. Todas siguen en modo de investigación.
use nqc_666_event_pressure::engine::Engine;
type SingleWrite = Engine<false, true>;
type BatchOnly = Engine<true, false>;
type Combined = Engine<true, true>;
```

Las muestras usan posiciones sintéticas y cálculos/obligaciones preparados.
No representan tráfico observado ni una promesa de latencia del bot completo.
