# Auditoría H2E — GitHub Actions en rama Omega

Fecha: 2026-10-22. Auditoría de preparación completada antes de activar el flujo.
**H2 100% de integración y auditoría; certificación 0/36. Census abierto.**
Los dos gates físicos aprobaron en la cuarta corrida y su auditoría posterior
coincide con la lectura independiente de GitHub. Este porcentaje mide H2, no
la terminación del sistema ni la certificación de sus componentes.

Alcance: migración nueva bajo `omega/` y una única copia activa revisada en
`.github/workflows/omega-h2-audit.yml`; ninguna modificación al source histórico,
Miner, main o repositorio original.

## Resultado vigente por control

| Control | Evidencia y resultado |
|---|---|
| Checkout e identidad original | PASS; 637 payloads, objetos fuente y 106 workflows históricos desactivados |
| Omega | 314/314 en el commit publicado, sin skips, con D15B/D16 originales |
| Python Census | Regresión histórica clasificada en H2C: 664/838 en discovery, siete errores de preparación; otras 174/174 por sus CLI originales |
| Rust Census | 528/528 y build release en la tercera y cuarta corrida; fmt/Clippy auditados en H2C |
| Enlace PFT, Rust y Solidity | PASS en el productor nuevo; 56/56 Rust PFT y 14/14 Solidity |
| Forks históricos | PASS en tercera y cuarta corrida; 4/4, dos proveedores con resultados iguales |
| Replay desconectado completo | PASS en la cuarta corrida; 16 pasos originales verificados, fuente intacta y reproducción byte-idéntica |
| Certificación / autoridad económica | 0/36; Census abierto, artifact nuevo null, permisos económicos false |

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

## Cuarta corrida: productor corregido

Commit `e21d528dabd83d7f14e7f236b9e6d4e3fc1706f7`, árbol
`9964778862574102ac2cbe907d0f40ae6c78b847`, run
[39859932654](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39859932654),
attempt 1. Commit/tree se releen de la API y coinciden con la copia local limpia.
La regresión completa repetida sobre el commit publicado aprobó **314/314**;
SHA-256 del reporte `b501ac6a829afc20dedf712d7e7048d5f919aac15d5e51a434be2eef7e9c50cd`.

Forks, job `120107692904`: success, 41/41 pruebas del runner, 56/56 Rust PFT,
14/14 Solidity y 4/4 forks. Auditoría posterior de 29 compromisos, resultados
de ambos proveedores, identidad Git/run y aislamiento antes/después: PASS.
El resultado conserva exactamente el compromiso `historical-forks`
`96338bad40dd243f0199172507cdca42849f5c1c76cae87da1687ce1a3b5a260` de la tercera
corrida. Log de 488607 bytes: SHA-256
`ffbdfb56ee5f2531b56eac4a56e15c3730584b726930aa5ec41ea68a8b70aec2`.

La corrida anterior fallida se conserva: log replay de 135159 bytes, SHA-256
`3964570eb89b5d753ebceb2dc814f934bf879686ffa7894e35a636206c56abfc`;
20 compromisos recalculados, fuente autenticada y 528 tests comprobados, sin
`stage-complete`. El archivo original descargado conserva 6709740 bytes y
SHA-256 `1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4`.

### Replay aprobado y auditoría posterior

Replay, job `120107692521`: success. Fuente D06 autenticada por el verificador
original, 41/41 pruebas del runner, 528/528 Rust Census y build release PASS.
El replay físico transcurrió del `2026-10-22T21:47:58.975971Z` al
`2026-10-22T22:08:42.331238Z`: **1243.355267 segundos**. El timeout anterior de
1200 s era inferior a la duración requerida. El paso crash/resume tardó
1135.699 s; los dos current replay, 42.785 y 42.782 s. Se conservaron las pausas
originales y todos los casos, sin alterar el código histórico.

Auditoría del consumidor: **25 compromisos SHA-256 recalculados y 16 pares de
comandos STARTED/VERIFIED cotejados**, sin timeout ni comandos fallidos. Se
comprobaron run/attempt, commit/tree, fuente/ZIP original, timestamps y todos
los flags. El namespace real `net:[4026532315]` difiere del padre
`net:[4026531833]`, sólo contiene lo y no tiene red enrutable. El runner original
exige bind readonly, ausencia de rutas útiles y sockets físicamente inalcanzables.

`source_unchanged`, `current_replay_byte_identical`,
`history_replay_byte_identical` y `closeout_byte_identical` son true.
La raíz fuente y resultante es
`e3d2b0739d3e5affea6b337540cf3cb9b2caaedd438656d2759105d39dacba03`.
El compromiso del reporte `disconnected-replay` es
`6838ba1dc247eaefea5ca307115258b06d2a951105e68f1b07a454ec476530e8`.
Log de 155291 bytes: SHA-256
`2c3a05ce89358570256b6aa227f7051f9343dbfeaae3985f2e1425b459b6aa68`.

La API de GitHub confirma run `39859932654`, attempt 1, success, evento push,
workflow `393369697`, ambos jobs success en el grupo GitHub Actions con etiqueta
ubuntu-24.04, repositorio `1411047452`, rama y SHA exactos. El run terminó a las
22:08:46 UTC, después de la verificación. La consulta de artifacts devuelve
**total_count=0**. La identidad CI se auditó; la recertificación canónica sigue
false porque no existe artifact nuevo autenticado ni cierre de sus demás gates.

### Cierre del hito y siguiente alcance

La medición mantiene los cuatro controles originales: los tres primeros suman
75%; aislamiento, regresión Python clasificada, Rust y PFT/forks/replay completan
el último 25%. **H2 alcanza 100% de integración auditada.** Esto conserva los
siete errores históricos de preparación del discovery Python y sus 174 casos
validados separadamente; no declara verde ese discovery agregado ni el formato
PFT heredado. Las auditorías H2C/H2D conservan sus resultados y fechas originales.

Los nueve componentes Census conservan 7 foundational_partial y 2 historical_partial;
**0/9 Census y 0/36 Omega certificados**. El siguiente trabajo es producir y
autenticar evidencia CI por commit, poblar triadas independientes y el universo
completo de mercados/posiciones, completar adaptadores del alcance, integrar
grafo/libro/oráculos, poblar ledger y reconciliar costos, y demostrar durabilidad,
recuperación y reorgs del Evidence Vault. Luego se cierran gates por componente.
H2 100% no es un porcentaje global de Omega ni autorización para Shadow/Canary.

El productor físicamente probado es `e21d528dabd83d7f14e7f236b9e6d4e3fc1706f7`.
El commit posterior de esta auditoría cambia únicamente documentación; no se
atribuye a ese SHA posterior la corrida del productor. Todo permanece en la rama
Omega y el PR 30 en borrador; Miner, main y source original no se modifican.
