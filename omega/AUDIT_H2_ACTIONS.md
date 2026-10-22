# Auditoría H2E — GitHub Actions en rama Omega

Fecha: 2026-10-22. Auditoría de preparación completada antes de activar el flujo.
**H2 93.75% (94% redondeado), certificación 0/36.** Hay resultados físicos parciales
remotos; los dos gates completos siguen pendientes. La autorización del usuario
abarca el nuevo flujo en la rama Omega.

Alcance: migración nueva bajo `omega/` y una única copia activa revisada en
`.github/workflows/omega-h2-audit.yml`; ninguna modificación al source histórico,
Miner, main o repositorio original.

## Preparación: revisión y pruebas locales

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

## Estado al publicar la preparación

Los resultados unitarios son fixtures, no namespaces ni forks físicos. El
container local conserva su bloqueo de unshare/RPC documentado. El seed D06
fue leído desde GitHub: artifact 11143129177, digest original, expired=false;
su acceso desde el token de una corrida nueva todavía debe probarse.

La preparación debía publicarse antes de la única copia activa en la misma rama.
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

La segunda corrida `39855080042`, commit `33c788b08fcfa3302e98f40a4d31cfdfe10e3386`,
pasó namespace, aislamiento con objetos originales y 31/31 tests nuevos en replay.
Se detuvo antes de descargar D06 por la validación local del token, demasiado
restrictiva (sólo alfanuméricos/underscore). Se ajustó al alfabeto Bearer RFC 6750,
sin mostrar ni inspeccionar la credencial. Se mantienen el rechazo de inyección
CR/LF/comillas y la entrega por stdin a curl. Se añade regresión de token opaco.
No se interpreta ese fallo de validación como denegación de acceso entre repositorios.

El job forks de esa segunda corrida completó enlace PFT, 56/56 Rust y 14/14
Solidity; falló después con HTTP 403 en el preflight urllib. Se cambia únicamente
la consulta de preflight a curl normal, como en Termux, y se registran ambos
proveedores, método, estado y motivo antes de compilar. No hay cambio de RPC,
túnel, credencial ni relajación del requisito de consenso. HTTP 200 con error
JSON-RPC tampoco pasa. Se añade cobertura de transportes y diagnóstico de ambos.

Regresión completa tras las correcciones: **310/310**, 0 skipped/errores/fallos,
con D15B/D16 auténticos. Aislamiento completo con objetos fuente: PASS, 76 archivos
de extensión, 1 workflow Omega exacto, 0 workflows históricos activos. Al publicar
esa corrección, el cambio de transporte aún requería una corrida física.

## Tercera corrida: forks físicos aprobados

Productor `81328bd216623e12e3743437f79c17decf88ad24`, árbol
`7c5afb9a4e8219cd4e543035b787a58d5210634c`. Workflow ID `393369697`, run
[39856119444](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39856119444),
attempt 1, evento push, repositorio `1411047452` y rama Omega exacta.
Se leyeron commit/tree y jobs independientemente mediante la API de GitHub.

El job forks `120094656747` finalizó success. Ambos RPC pasaron el preflight;
el runner reprodujo el enlace PFT con HEAD limpio, 37/37 pruebas propias,
56/56 Rust PFT, 14/14 Solidity y **4/4 ejecuciones históricas** (positivo y
rechazo atómico por cada proveedor). El bloque es 25252136 y la transacción
`0xc953d5da04ee4dc9f421ac5418f05add5244d9816c50420bbf7bb6cbafc1150a`.

Auditoría posterior: se recalcularon los 29 compromisos SHA-256 del job, los
conteos y la igualdad de resultados de ambos proveedores. Se repitió localmente
`compare_forks` sobre los JSON originales de los logs. Aislamiento antes/después
idéntico; todos los comandos registrados terminaron con código 0; producer,
commit/tree, run/attempt y stage-complete coinciden. Resultado físico:
`PHYSICAL_GATE_PASS`. El protocolo conserva `NOT_CLOSED` y todas las autoridades
económicas false. El resultado del fork es una simulación histórica y no P&L
real de NQC.

Log descargado del job forks (487055 bytes, con salto final): SHA-256
`08eb22592f8b5ad5f47d6ee0917d1bc58fdecb7bb8798b15f683d9e8c9cb59a7`.
Compromiso `historical-forks`:
`96338bad40dd243f0199172507cdca42849f5c1c76cae87da1687ce1a3b5a260`.
Regresión local completa de 310 pruebas, SHA-256 del JSON:
`e1df9d58c60d50ac37d889ffe11db2873abfcec4f72fecea9f57e0a56a57439f`.

### Replay: límite de ejecución identificado

El job replay `120094657212` de la tercera corrida terminó failure: la llamada
al runner histórico alcanzó el timeout genérico de 1200 segundos. Antes aprobó
la descarga y autenticación original de D06, 528/528 Rust y build release. El
replay arrancó a las 21:20:00 UTC y fue interrumpido a las 21:40:00 UTC. No hay
`stage-complete` de replay ni cierre de H2 para esta corrida.

El diagnóstico local separado verificó el store con Rust y Python originales.
El current replay release tardó 43.25 s y terminó 0. La inspección del código
inmutable confirmó que `RpcClient::pace` conserva las pausas por proveedor
también en replay. La matriz histórica tiene 755 intercambios, 70 manifiestos
y cinco cortes de interrupción/recuperación. Ese trabajo no se elimina ni se
acelera alterando el reloj, proveedores o aserciones.

Se añade un observador de comandos que carga el runner por su Git blob original
`a200f6d699df693f4087c6b7dc2c9027898ebba4`. Delega sin cambiar argumentos, resultados
ni excepciones; sólo registra inicio, aceptación y duración de cada llamada.
El supervisor conserva stdout parcial en timeouts. GNU timeout limita a 3000 s
el grupo de procesos root (TERM, KILL tras 30 s); el límite exterior es 3060 s
y el job sigue limitado a 60 minutos. No se modifica el workflow revisado.

Regresión tras el observador: **314/314** con D15B/D16 auténticos y aislamiento
completo PASS. Cuatro pruebas nuevas verifican delegación intacta, propagación
de rechazo, rechazo de un blob alterado y conservación de evidencia al agotar
el tiempo sin emitir éxito. Sigue pendiente auditar una corrida física completa.
