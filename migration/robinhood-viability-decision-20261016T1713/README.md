# Cierre de viabilidad acotado — 16/oct/2026

Base PR25 `fc44cb648a3032922bcb5f31669e3155cc787807`. Segundo y último incremento
del presupuesto de dos acordado con Chavando; sin gasto. Ver `DECISION.md` y
`REOPENING.md`. Recomendación: congelar desarrollo activo hasta evidencia nueva de
admisión y una vía financiable sin capital/deuda personal.

Se añadió un preflight de sólo lectura con versiones resueltas desde el Yarn lock
fijado y comparación de 12 archivos contra el commit del bundler. Detecta ausentes
y versiones/entradas incorrectas; nunca instala, importa ni ejecuta JavaScript.
Salida 1 = requisitos ausentes; salida 0 sólo = requisitos necesarios encontrados,
nunca admisión, integridad completa ni compatibilidad. Los errores de pin/lock
abortan sin fabricar un informe. No es un resolvedor universal de Node.

Resultado real: cuatro paquetes externos necesarios ausentes y tres entradas de
workspaces sin compilar. `evidence/environment.json` contiene candidatos, versiones,
rutas y hashes. Es inventario del entorno a las 17:12:40 UTC, no captura blockchain.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s migration/robinhood-viability-decision-20261016T1713 -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python migration/robinhood-viability-decision-20261016T1713/probe_environment.py --checkout /tmp/nqc-reference-v07 --node-modules /tmp/nqc-reference-v07/node_modules --node-modules /tmp/nqc-bundler-env-20261016/node_modules --node-modules /opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules --yarn-cache /usr/local/share/.cache/yarn/v6
```

La revisión documental añade límites de proveedores, discrepancia de Unlinked y
fuente oficial AA recuperada desde el enlace de navegación. No consultó servicios
de admisión ni saldos. No se lanzó ningún runner de capturas previo.

0 RPC locales/públicos, 0 segundos de captura blockchain, 0 firmas/transacciones,
0 instalaciones/gastos/contactos. La auditoría de PR25 es replay offline de datos
existentes, no diez RPC nuevos. Rust/Solidity sin cambios ni ejecución.

Verificación de este incremento: 21 pruebas Python aprobadas (12 nuevas y 9 de
aislamiento), auditoría offline PR25 idéntica al informe registrado, 21 manifiestos
previos intactos y 45 entradas de locks comprobadas (10 de este incremento y 35 de
PR25; no se afirma que sean fuentes distintas). 377 blobs originales conservados,
106 workflows deshabilitados y cero activos. Logs en `evidence/verification/`.
