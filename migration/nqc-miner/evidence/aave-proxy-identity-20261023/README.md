# Identidad histórica del proxy — 2026-10-23 UTC

La sonda completó 72 consultas públicas de solo lectura entre
01:04:07 y 01:07:51 UTC. Los tres bloques son 26248075, 26248113 y 26248378,
inmediatamente anteriores a los eventos de la captura Aave ya auditada.

En los tres puntos, PublicNode y dRPC devolvieron:

- Implementación: `0x728a138a4823392c2efa55e028d434f526fe03cf`.
- Runtime de implementación: 21146 bytes.
- SHA-256 del runtime: `fbd5bf315821d290d18b3a06cafb2f69457075388eae50b6134f490cf83cb049`.
- SHA-256 del proxy: `bf8a408a1f5440c167d91fa2d972deb23bb4d809e8dd089009885ec88a826f88`.

El registro oficial Aave Ethereum consultado contiene la misma dirección de
implementación. Eso corrobora la dirección; no verifica una compilación, versión
ni correspondencia semántica con una rama de fuentes. Véanse las referencias
identificadas por blob en `docs/aave-version-gates.md`.

`audit.json` reproduce offline las 72 respuestas con sus solicitudes y vuelve
a calcular direcciones y hashes, comprobando la identidad de los informes fuente
contra la publicación `f7a96bc0ba7af395453491cb001f1648b42e4864`. Los bytes de
runtime y slot están completos; los encabezados se conservan como proyecciones
de número/hash/padre/timestamp. No hay prueba criptográfica de estado.

`tests.txt` conserva **7 pruebas aprobadas**: discrepancias, reorg tras el quorum,
cadena/finalización ajenas, estado ausente, slot inválido, límites de bytecode,
fuentes ajenas y rechazo de métodos o parámetros no permitidos antes de abrir
una conexión. El CLI y sus fuentes Rust no se modificaron en esta continuación;
las 167 pruebas Rust y 242 Python del bloque anterior no se repitieron.

Reproducción offline desde `migration/nqc-miner`:

```bash
python3 -m unittest discover -s evidence/aave-proxy-identity-20261023 -p test_probe.py -v
python3 evidence/aave-proxy-identity-20261023/audit.py --output /ruta/nueva/auditoria-proxy.json
```

`capture.py` es una sonda de investigación acotada a esos tres informes y a dos
endpoints públicos fijos. No amplía los métodos del CLI de Miner ni añade un
servicio productivo. Conserva los fallos como incompletos y no certifica datos
parciales. No se reejecuta como parte de la auditoría offline.

No se extrapolan estos tres puntos a los 48 estados ni a otras cadenas. Versión,
fuente de implementación, frescura del oráculo y elegibilidad siguen pendientes
de certificación. Los resultados enriquecen los mismos eventos, sin sumar nuevas
liquidaciones. Avance **43/100**, observador intacto y operación desactivada.
