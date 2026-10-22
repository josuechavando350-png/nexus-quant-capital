# Miner: continuación auditada del 22 de octubre de 2026

## Alcance y resultado

Se trabajó en una copia Git y rama propias, exclusivamente dentro de
`migration/nqc-miner/`. Se incorporó la revisión de Miner `561c846` ya publicada
durante el trabajo, conservando ambos historiales. No se modificó la rama del
observador, su estado, sus servicios ni sus credenciales. No hay firma, envíos de
transacciones, alertas, gasto o despliegue operacional.

El código auditado final es **`a841261f9c13b255905deaeef75d5b42cb8814e1`**.
Los commits posteriores de esta entrega agregan documentación y evidencia; las
capturas conservan la identidad original, sin atribuirse retrospectivamente un
SHA nuevo. La revisión fue realizada por el mismo agente con reproductores y
herramientas separadas; no constituye una auditoría externa independiente.

## Fallos reproducidos y correcciones

1. **Escritura fuera de la carpeta prevista.** El binder resolvía enlaces con
   `Path.resolve()` y podía escribir en otra carpeta. Además, comprobar existencia
   antes de `os.replace()` permitía sobrescribir al ganador de una carrera.
   Ahora recorre directorios por descriptores con `O_NOFOLLOW`, prepara un archivo
   temporal y lo publica mediante un enlace atómico que falla si el destino ya
   existe. Las pruebas incluyen un enlace hacia una carpeta ajena, un enlace
   colgante y ocho escritores simultáneos: solo uno gana y ningún archivo se
   sobrescribe. Son garantías para esas operaciones POSIX, no frente a un
   administrador hostil del sistema operativo.
2. **Validación ambigua de identidad.** Se rechazan sustituciones `false`/`0`,
   identidad fuente ausente, compilador desconocido, JSON no finito y entradas
   sobredimensionadas. Se conserva la recomputación v2 del hash de compilación.
3. **Capturas difíciles de auditar.** `capture_run.py` conserva configuración,
   stdout/stderr de cada paso, tiempos, errores, timeout, journal y reporte.
   Verifica propietario/build/ámbitos y hashes del ejecutable antes y después.
   Un proceso exitoso con ámbito incompleto, reorg, identidad ajena o datos
   provisionales no obtiene el estado de muestra completa. No registra valores
   de variables de entorno; los endpoints públicos elegidos se documentan aparte.
4. **Exportador incompatible con propietarios v2.** La actualización concurrente
   de Rust introdujo propietarios v2 mientras Python/JSON Schema aún exigían v1.
   El exportador y su esquema ahora admiten ambos formatos sin convertir los
   journals anteriores, preservan la identidad del build y rechazan mezcla de
   identidades. La prueba v2 usa el verificador Rust y Polars reales.
5. **Gate de formato pendiente.** La batería inicial falló en `rustfmt` sobre
   el test HTTP publicado. Se conserva ese fallo y se corrige su formato.

## Auditoría ejecutada

| Revisión | Rust | Python | Resultado |
|---|---:|---:|---|
| Base `d3fcff5` | 138 PASS | 47 PASS | FAIL global: rustfmt |
| Corrección de aislamiento/captura v1 | 138 PASS | 59 PASS | PASS integral |
| Integración final v2 `a841261` | **141 PASS** | **64 PASS** | **PASS integral** |

Las repeticiones no se suman como tests nuevos. La última batería incluye build
offline con lock, Clippy sin advertencias, rustfmt, pruebas, aislamiento y
recomputación de la identidad. No hubo tests ignorados. Logs, manifiestos de
entradas y hashes están en `evidence/offline-v2-isolation-20261022/`; los intentos
anteriores se preservan en `offline-baseline-20261022/` y
`offline-isolation-20261022/`.

Rust 1.90.0, target `x86_64-unknown-linux-gnu`, perfil debug:

```text
source_sha256=f1c9fe6516836cb5e3916684f74061ae4b3cb7b245cf9044a8876f24b62799b1
build_identity_sha256=3cd0fd043fc2befe037ad67f679e16cfcea9ceddadf83a1cda2991dd69061c97
cargo_lock_sha256=634f6b4361a2b29a6eeb55338422f5dbb0902fefa231433bfd385b6240a0daab
```

## Dependencias: alcance completo del lock

`cargo-audit 0.22.2` examinó 385 entradas del lock contra 1,349 advisories de
RustSec, revisión `640bf5a9f06e66d8721e8772766531fe77c8630d`, sin ignorar avisos,
sin filtros por plataforma y con comprobación de versiones retiradas habilitada.
Resultado: **0 vulnerabilidades conocidas aplicables, 2 avisos de mantenimiento**.

- `derivative 2.2.0`: entrada opcional del lock, ausente del árbol activo al
  consultar todos los targets.
- `paste 1.0.15`: proc-macro de compilación transitiva de Alloy/REVM. Su falta de
  mantenimiento queda como deuda abierta; no se suprime el aviso ni se afirma que
  cero vulnerabilidades conocidas equivalga a ausencia de defectos.

Reporte, stderr e identidad de la base están en
`evidence/dependencies-full-20261022/`. El contenido del lock coincide con el
compilado. Los servidores externos y Nix no se consideran auditados por esto.

## Lectura pública durable

Dos ejecuciones distintas de la misma selección técnica se conservan por separado;
sus eventos **no se suman**. La muestra v1 pertenece a `39fd15c`; la final v2 a
`a841261`. Ambas terminaron con 4 ámbitos completos, 3 eventos canónicos y hashes
del ejecutable iguales antes/después. Se usa acuerdo entre dos endpoints por
cadena; esto no demuestra independencia de operadores ni prueba criptográfica
del estado de la cadena.

| Cadena / ámbito | Bloques inclusivos | Eventos |
|---|---|---:|
| Ethereum / Aave V3 | 26,248,000–26,248,399 | 3 liquidaciones |
| Ethereum / Morpho Blue | 26,248,000–26,248,399 | 0 |
| Base / Aave V3 | 52,950,023–52,950,122 | 0 |
| Arbitrum / Aave V3 | 517,288,425–517,288,524 | 0 |

La ventana Ethereum se seleccionó para incluir transacciones previamente
indexadas: **no es una muestra aleatoria ni estima frecuencia o rentabilidad**.
Cero eventos en las otras ventanas no significa ausencia de oportunidades.

La captura final está en `evidence/public-capture-v2-20261022/`; conserva 17
registros (3 eventos, 10 lotes y 4 cierres de ámbito). Su exportación local en
`evidence/public-parquet-v2-20261022/` pasó verificación Rust y roundtrip Parquet
con conservación exacta de bytes. Los manifiestos de captura y schemas de
propietarios v1/v2 y Parquet se comprobaron después de copiar la evidencia.

La saturación sigue en `insufficient_data`: faltan primera elegibilidad y
propinas. La cobertura histórica del universo escaneado tiene denominador 3;
no había registro prospectivo de vigilancia y el informe conserva 0/3 vigiladas.
Eso no acredita cobertura global ni detección anticipada. Ganancia realizada:
**no medida**, no cero estimado ni ganancia simulada convertida en real.

## Aislamiento y pendientes

El verificador mantiene 531 archivos fuente importados, 106 workflows
deshabilitados y 0 activos. El diff contra `16e3522` no toca archivos fuera del
subárbol Miner. Los tests locales abren listeners HTTP efímeros; las capturas
públicas solo realizan lecturas. El gasto autorizado y utilizado por Miner es 0.

El progreso ponderado final se conserva en `progress.json`: se acredita la nueva
auditoría integral, la muestra pública verificada y la entrega Git aislada. No se
acredita ninguna salida operacional A–D. Faltan servicios propios operativos y
recuperables, calibración económica multichain, túnel causal, ventana prospectiva
Shadow, certificación de adaptadores, autorización concreta de Canary y datos
realizados para validar el aprendizaje. El puente del observador permanece
desactivado por la instrucción del usuario.

## Publicación y reproducción de la identidad local

La subida Git directa no tenía credenciales en el entorno. La entrega se publica
mediante la conexión GitHub, en una rama nueva, con el mismo árbol de archivos.
El commit de publicación tiene su propia identidad; no se sustituye el SHA de las
capturas. `evidence/source-history-20261022.bundle` conserva los commits locales
`39fd15c`, `a841261` y `2ff98f1` con sus padres reales. `git bundle verify` pasó.
Los prerrequisitos `d3fcff5` y `561c846` pertenecen al historial publicado de Miner.

Para recuperar las revisiones auditadas en una copia del repositorio que ya tenga
esos prerrequisitos, desde la raíz del repositorio:

```bash
git fetch migration/nqc-miner/evidence/source-history-20261022.bundle \
  feat/nqc-miner-audit-20261022:refs/heads/miner-audited-snapshot
```

El código ejecutado se puede inspeccionar en `a841261`, y el journal mantiene esa
identidad. El bundle no contiene ejecutables, credenciales ni datos del observador.
