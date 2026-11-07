# SUPERHUNTER — Slither: control positivo + control limpio, ambos OWNED

**Sucesor del PR #71.** Adaptador #6 del portafolio. Estado: **ADAPTER_IN_LAB** (comparación programada, ejecución real no certificada). **No** se ha instalado Slither ni solc en un host del usuario, ni se han ejecutado escaneos externos, ni se ha desplegado un sandbox sin red.

## Qué cambió y por qué

El PR #71 exigía que un contrato propio y deliberadamente defectuoso activara el detector de Slither `tx-origin`. Eso evita un falso PASS cuando el scanner no devuelve alertas, pero **no mide si también genera una alerta sobre código que no tiene ese defecto**. Añadimos un segundo control obligatorio:

- **Positivo:** `Owned.sol` de 288 bytes con `require(tx.origin == owner, "owner")`, SHA-256 `ef5475a13e367bef34010e339c082c85383ab85e4f229cd607899f5f52ce0c64`. Esperamos **exactamente una alerta `tx-origin` ligada a origen**.
- **Limpio:** el mismo control de 289 bytes, pero usando `require(msg.sender == owner, "owner")`, SHA-256 `f4435d614ec0d890f56f06c6250bba4a60152255fa3f8d5ceec13952f9aba0f1`. Esperamos **cero alertas**.

Se reutiliza el compilador `solc 0.8.30` fijado y la admisión de `slither-analyzer 0.11.6` + `crytic-compile 0.4.2`. Se conserva el worker supervisado, sus presupuestos por proceso y los controles de hash. El modo `clean` exige el hash exacto del segundo fixture: no permite objetivos, bytecode ni parámetros arbitrarios.

Cada ejecución se importa por `static_review` a un subexpediente independiente con manifiesto. El verificador compara fuente, número de hallazgos, ID del detector, versión declarada, scope y **mismo commit declarado**. Los contadores exigen `int`, nunca booleanos. El expediente conjunto publica `COMPLETE.json` **solo después** de pasar ambos; los expedientes parciales se rechazan.

## Comandos para un entorno de laboratorio previamente autorizado y preparado

```bash
python3 -m superhunter doctor-owned-slither --solc /privado/solc-oficial-verificado
python3 -m superhunter run-owned-slither-pair \
  --solc /privado/solc-oficial-verificado \
  --repo-commit COMMIT_DE_40_HEX \
  --out /privado/slither-pair-nuevo
python3 -m superhunter verify-owned-slither-pair \
  --bundle /privado/slither-pair-nuevo
```

Las órdenes de escaneo requieren un entorno con dependencias revisadas y las restricciones de host/red apropiadas. **Este adaptador no crea una sandbox de red**. Solo acepta las dos fuentes OWNED fijadas, no un repositorio externo. No usarlo para objetivos ajenos.

## Estado de pruebas, sin sobredeclaración

- Se ejecutaron **13/13 comprobaciones focalizadas locales** (Python 3.13, stubs de componentes del paquete que no estaban presentes). Incluyeron detección positiva sintética, falso positivo sobre el caso limpio, conteos booleanos, hashes y commits distintos, bloqueo por scanner ausente y verificación de contenedor modificado/resellado.
- La nueva prueba de GitHub `test_slither_control_pair.py` declara sus propias regresiones, incluida la coherencia de commits, pero **todavía no se ha ejecutado en una checkout completo de SuperHunter**. El QA general y EVM no se reejecutaron.
- El entorno del evaluador no dispone de Slither/solc ni de acceso DNS a sus distribuciones. **No existe evidencia de una ejecución real del scanner** en esta iteración.
- Los reportes fabricados dentro de tests son **sintéticos**, nunca hallazgos originales. Las verificaciones de hashes y scope no autentican al productor. `network_isolation_proven=false`, `independent_execution_replay=false`, `vulnerability_confirmed=false`.

## Para IAs que retomen el trabajo

1. Leer `AGENTS.md`, `SUPERHUNTER_STATUS.md`, `REPOSITORIES_50.md` y `SLITHER_OWNED_LAB.md` antes de usar el nuevo gate.
2. Verificar cabeza de los PR #68–#72 y trabajar en rama separada; no modificar NQC histórico o activar workflows.
3. Primer criterio externo pendiente: instalar Slither/solc auditados **en sandbox con egress denegado**, ejecutar ambos casos con reportes genuinos, confirmar que fuente y versión coinciden y repetir el análisis en entorno independiente.
4. Ejecutar QA completo de la rama, conservar todos los IDs históricos y publicar evidencia con hashes. Solo después considerar #6 `INTEGRATED_BOUNDED`.
5. No inferir generalización, precisión global, bounty, ni avance global de los 50 proyectos a partir de dos fixtures conocidos.

**En resumen:** el cambio añade una prueba diferencial más rigurosa y dos expedientes reproducibles; **sigue sin constituir una integración externa certificada**.

## Sucesor: comparación offline de dos pares

[SLITHER_PAIR_REPLAY.md](SLITHER_PAIR_REPLAY.md) documenta la comprobación de dos pares completos con dos hashes SHA-256 que deben haberse guardado fuera de los paquetes antes de verificar. Exige coincidencia de los resultados normalizados y bloquea alteraciones/resellados; no ejecuta Slither ni certifica que los productores sean independientes.
