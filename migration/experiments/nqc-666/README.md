# NQC 666 — laboratorio reproducible

Investigación aislada, sin ejecución pública ni autorización comercial.

- [Informe y mediciones](REPORT.md)
- [Arquitectura, 18 roles y límites](ARCHITECTURE.md)
- [Protocolo de medida](PRE_REGISTER.md)
- [Datos agregados reproducibles](evidence/summary.json)
- [Procedencia y estado verificable](PROVENANCE.json); [manifiesto SHA-256](MANIFEST.sha256).
- Fuentes: `src/`; adversariales: `tests/adversarial.rs`; originales preservados: `historical/`.

## Requisitos

Linux x86_64 para el instrumento; Rust **1.90.0**, Cargo, g++, make, objdump y
Python 3.12. El paquete Rust no tiene dependencias externas. La toolchain debe
estar instalada antes de los comandos `--offline`. El compilador exacto utilizado,
CPU, flags, afinidad y hashes binarios constan en cada `evidence/run*/benchmark.json`.
No instala servicios, no usa credenciales ni configura una máquina por cuenta del usuario.

## Verificación rápida

Desde la raíz del repositorio:

```sh
python3 migration/verify_isolation.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s migration -p test_isolation.py
cd migration/experiments/nqc-666
sha256sum -c MANIFEST.sha256
CARGO_TARGET_DIR=/tmp/nqc666-tests cargo test --locked --offline
python3 scripts/verify_evidence.py
```

El verificador de evidencia recalcula todos los percentiles desde los `.bin`
little-endian contenidos en los ZIP, verifica sus hashes y comprueba el resumen
agregado. No necesita red ni compilador. No recalcula p99 a partir de otros p99.

## Reproducir desde cero

Use directorios de salida nuevos **fuera del repositorio**. No corra mediciones en
paralelo ni junto con otras compilaciones; la VM puede tener carga ajena no controlable.

```sh
python3 scripts/reproduce.py --out /tmp/nqc666-matrix
python3 scripts/reproduce.py \
  --out /tmp/nqc666-inline \
  --baseline-existing /tmp/nqc666-matrix/baseline/NQC_019 \
  --refinement
```

El primer comando extrae el ZIP original en una copia, verifica su manifiesto y
sus 3,1 millones de muestras históricas, reconstruye C++, ejecuta regresiones,
sanitizadores, baseline nuevo y matriz Rust. El segundo mide la última variante
inline con los mismos corpus. Las latencias no serán idénticas entre máquinas;
las entradas, semántica, configuración, muestras y percentiles sí son auditables.

Si LeakSanitizer falla por acceso a `/proc`/ptrace, el script conserva el error y
ejecuta ASan/UBSan sin detección de fugas, rotulándolo por separado. No modifica
las fuentes o tests originales para ocultarlo. Una repetición diferente puede
tener otro estado de LSAN; compruebe los logs de esa repetición.

La opción `--baseline-existing` sólo reutiliza una copia de baseline ya validada;
no la presente como una reconstrucción nueva. Se utilizó así para no recompilar
innecesariamente los originales en cada refinamiento de NQC666.

## PGO opcional, descartado para la configuración recomendada

Requiere el componente oficial `llvm-tools` de Rust 1.90.0. Entrena y evalúa sólo
fixtures; no presume un dataset representativo del mercado:

```sh
python3 scripts/pgo.py --out /tmp/nqc666-pgo \
  --matrix /tmp/nqc666-matrix \
  --baseline /tmp/nqc666-matrix/baseline/NQC_019
```

Los resultados originales de PGO corresponden al snapshot anterior al último
inline y se conservan con su perfil de entrenamiento. No se atribuyen al último
binario. No hubo mejora integrada consistente; no es la vía recomendada.

## Uso del componente

`Engine::new` registra claves explícitas. `on_event` recibe una actualización
completa decodificada; `candidate` devuelve un ticket local; `finalize` revalida
el dinero, identidad, tiempo y secuencia. `commercial_admission` es siempre falso.
Los campos no autentican por sí mismos datos ni contratos de terceros.

Para una compilación experimental de latencia baja en el host ensayado:

```sh
CARGO_TARGET_DIR=/tmp/nqc666-build cargo build --profile fat --locked --offline
```

Fat LTO es una opción experimental de compilación; `release` portátil permanece
disponible como referencia. No se cambia ningún motor histórico ni se conecta
esta librería al trading, a RPC o a un builder.

## Organización de resultados

| Carpeta | Corte de investigación |
|---|---|
| `run1_initial` | Primera integración, doble cálculo frente a reutilización; filtro de 32 bytes. |
| `run2_compact` | Filtro de 24 bytes; procedencia sintética explícita; ventana completa de envío. |
| `run3_copyfree` | Elimina copia financiera; compara C++ intercalado, LTO, native. |
| `run4_pgo` | PGO contra fat LTO del corte 3; no adoptado. |
| `run5_inline` | Corte final, mismo filtro integrado en el llamador; release/fat y baseline C++ intercalado. |

Cada corte guarda fuentes o identifica el snapshot usado, resultados y todas las
muestras, incluidas colas desfavorables. Los binarios no se distribuyen como
ejecutables autorizados; sus hashes y desensamblados permiten auditar la medida.
