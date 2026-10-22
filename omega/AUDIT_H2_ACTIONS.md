# Auditoría H2E — GitHub Actions en rama Omega

Fecha: 2026-10-22. Auditoría de preparación completada antes de activar el flujo.
**H2 93.75% (94% redondeado), certificación 0/36.** Todavía no hay resultado físico
remoto. La autorización del usuario abarca el nuevo flujo en la rama Omega.

Alcance: migración nueva bajo `omega/` y una única copia activa revisada en
`.github/workflows/omega-h2-audit.yml`; ninguna modificación al source histórico,
Miner, main o repositorio original.

## Revisión y pruebas locales

- Omega completo: **303/303**, 30 pruebas nuevas; 0 skipped, errores o expected
  failures. D15B y D16 originales suministrados a las pruebas de archivo real.
- Rust Census: **528/528**, 0 fallos o ignoradas, Rust 1.98.1, workspace/all-targets,
  locked/offline y target externo. No se modifica ninguna fuente Rust.
- Aislamiento completo con objetos fuente: 637 payloads, 531 fuentes, 106
  workflows históricos desactivados, 0 activos históricos. Preparación sin
  activación: 0 workflows Omega. En copia desechable con activación exacta: 1
  workflow Omega y PASS. Otro workflow agregado es rechazado por el original.
- Harness de fork producido por `prepare_harness`: compilación física offline
  con Foundry 1.7.1 y solc 0.8.24 aprobada. Conserva la advertencia histórica
  unsafe-typecast; no se reescribe el test recuperado.
- YAML parseado, Python AST y `git diff --check` aprobados. Action checkout
  `11d5960a326750d5838078e36cf38b85af677262` comprobada en el repositorio oficial.

Las pruebas adversariales rechazan repositorio/ref/evento/runner/commit/tree
equivocados, rama Miner o main, run IDs malformados, workflow alterado incluso
si se altera también la plantilla, symlinks/modos ejecutables, RPC de escritura,
batches mixtos, costos/reservas null, bool tratado como número, ganancias cero
o no conciliadas, desacuerdo entre proveedores y casos negativos incompletos.
La descarga rechaza HTTP, destinos de API ajenos al source, tokens malformados,
hashes incorrectos y sobrescritura. Se prueba que el token no aparece en argv
ni en el entorno del proceso hijo y que no se usa location-trusted.

La auditoría encontró un límite de descarga demasiado pequeño para Foundry:
el asset original mide 98,596,412 bytes. El límite pasó de 64 a 128 MiB y conserva
SHA-256 `cf7e688ed0c4c48adffca788b496076e31060b67ac5afe1e43dbb5499c20c88b`.
También se endureció la aceptación de números para rechazar bool/null y la
suite del runner utiliza el recorder estricto que no convierte skips en PASS.

## Pendiente de ejecución remota

Los resultados unitarios son fixtures, no namespaces ni forks físicos. El
container local conserva su bloqueo de unshare/RPC documentado. El seed D06
fue leído desde GitHub: artifact 11143129177, digest original, expired=false;
su acceso desde el token de una corrida nueva todavía debe probarse.

Se publicará esta preparación y después la única copia activa en la misma rama.
Se deben leer commit/tree/run/attempt/jobs/logs al finalizar. Una corrida exitosa
sin artifact nuevo autenticado no certifica Census. La política de no uploads
ni caches mantiene ese campo null y evita introducir esos consumos facturables.
El discovery Python Census conserva sus siete errores heredados de preparación.

## Primera corrida física y corrección

Preparación publicada en `a82ab1bbb47c592f1f6f65fda944a09cc735358e`;
activación en `800d545aa857d0454f4a095ba4c82aadd26aa30c`, árbol
`0536a17cd8e805c5e1604f3155ec48f25f1216cb`. GitHub run `39854791127`, attempt 1,
confirmó la rama correcta y ejecutó ambos jobs en Ubuntu estándar. El probe real
de namespace y bind mount readonly pasó en ambos. No pasó el gate completo:
sudo eliminó PYTHONDONTWRITEBYTECODE y el intérprete hijo creó omega/__pycache__;
el verificador rechazó correctamente ese directorio adicional.

Corrección: `-B` explícito para ambos Python bajo sudo y `sys.dont_write_bytecode`
antes de imports locales. Una prueba de regresión ejecuta el script en otro
proceso sin esa variable de entorno y exige ausencia de __pycache__. No se
oculta/borra el directorio para forzar PASS ni se debilita el inventario.
Se repetirá el gate sobre el commit corregido; esta corrida fallida se conserva.
