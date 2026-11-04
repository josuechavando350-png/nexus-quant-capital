# Registro de validación — adaptadores offline

## Ejecutado en esta sesión

- Python 3.13.5, Linux; sin instalación de dependencias.
- Los archivos originales `bridge.py`, `__init__.py`, `__main__.py` y
  `tests/test_bridge.py` se materializaron y verificaron por Git blob SHA contra
  el commit remoto `fde16ea61884c85aeef7d7e7ae2bdd7f5bf1b14c`.
- Baseline original: **32 tests, 0 fallos, 0 errores, 0 omisiones**.
- Después de los cambios: **67 tests, 0 fallos, 0 errores, 0 omisiones**.
- Compilación de los módulos Python: correcta.
- Smoke de compatibilidad: se importó únicamente el archivo de dataclasses de
  DIABLO, después de comprobar su blob SHA. Se construyó un Finding con datos
  sintéticos y se exportó sin promover su severidad.
- El archivo nativo NQC Protocol/Fork se verificó contra su blob SHA y produjo
  `INCOMPLETE`, sin borrador ni hallazgo. No fue tratado como una reconstrucción.
- Ese smoke y la prueba de integración bloquearon sockets y subprocesses.

## Regresiones cubiertas

ID estable, asociación de solicitud, cadena y bloque; dirección o PoC
incorrectas; artefactos alterados; datos económicos incompatibles; confianza o
severidad no ligadas al documento; claves JSON duplicadas; NaN/Infinity; tipos
malformados; uint256; dígitos Unicode no válidos; traversal y symlinks; FIFOs;
límites de tamaño; permisos de salida; no sobrescritura; ida y vuelta CLI;
feedback a DIABLO; documentos históricos NQC no promovidos a hallazgos.

Las 32 pruebas originales conservan sus comprobaciones de rechazo. Las pruebas
positivas ahora exigen `REVIEW_REQUIRED`, un `draft` y ausencia de confirmación.
El fixture NQC incluye la Reconstruction completa, porque el contrato ya no
acepta que severidad o confianza queden fuera de la evidencia ligada.

## No ejecutado / no demostrado

- No se ejecutó Forge ni ninguna PoC Solidity.
- No se corrieron los motores de descubrimiento ni reconstrucción.
- No se hicieron peticiones RPC ni operaciones contra contratos de terceros.
- No se validó un hallazgo real, scope vigente o elegibilidad para recompensa.
- No se ejecutó la suite completa Rust/Python histórica de NQC ni su verificador
  de aislamiento. No hubo checkout completo: git por red no estaba disponible.
  La revisión de aislamiento de esta entrega se limita al diff remoto, que debe
  contener únicamente cambios bajo `superhunter/`.
- No se ejecutó GitHub Actions ni se habilitó un workflow.
- La prueba positiva usa datos sintéticos. Los hashes prueban consistencia de
  bytes, no veracidad del productor, y un código de salida 0 no es certificación.

Los archivos `validation-results.json` y los logs de pruebas suministrados con
la entrega registran resultados locales. No sustituyen una ejecución CI
independiente ni certifican comportamiento de producción.
