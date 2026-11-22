# SUPERHUNTER · Plan maestro de las 20 herramientas

**Dueño:** Josue (josuechavando350-png) · **Ejecuta:** Astra · **Revisa:** Josue + Claude
**Fecha:** 22 de noviembre de 2026 · **Rama:** no tocar `main`, trabajar en ramas pequeñas con PR.

---

## Lo que este plan NO es

No es "conectar absolutamente todo al 100% y que nada quede afuera". Esa orden ya se intentó y dejó el repo con 213 ramas sin mergear, ciclos de "verificar la verificación" y **cero vulnerabilidades reales confirmadas** (ver `superhunter/ESTADO_PUBLICO.md`). Este plan corrige eso: pocas herramientas bien apuntadas, y una sola meta que se puede medir.

## Objetivo real y medible

Que el hunter encuentre **bugs reales**. La prueba que decide si sirve:

> Tomar 3 concursos ya cerrados de **Code4rena** o **Sherlock** cuyo reporte de hallazgos sea público. Correr el pipeline SIN ver el reporte. Medir cuántos de los bugs reales (High/Medium) encontró. Ese número es la calificación.

Mientras ese número sea 0, no se agregan más herramientas ni se "mejora la integración". Se arregla el pipeline hasta que suba.

## Reglas duras (para no volver al ciclo)

- Ni una herramienta nueva fuera de estas 20 sin que Josue lo autorice.
- Prohibido trabajo de "verificar que la verificación está verificada". Cada capa debe correr contra un **objetivo real** (un contrato de un concurso pasado), no contra sí misma.
- Cada entrega es una rama chica que se pueda probar sola. Nada de PRs gigantes encadenados sin mergear.
- Nada de inventar métricas de avance (ej. "40% listo"). Solo cuenta el número de la prueba ciega.
- No se toca NQC Defense ni `main`. Sin despliegues, sin fondos, sin objetivos sin permiso.

---

## Las 20 herramientas y su rol

**Estático — rápido y barato (marca sospechas):**
- `crytic/slither` — análisis estático base.
- `pessimistic-io/slitherin` — detectores extra para Slither.
- `Cyfrin/aderyn` — analizador estático en Rust.
- `Picodes/4naly3er` — el que Code4rena usa para su reporte automático.
- `semgrep/semgrep` — patrones peligrosos en cualquier lenguaje.

**Fuzzing e invariantes (intenta romperlo):**
- `foundry-rs/foundry` — base; fuzzing por invariantes.
- `crytic/echidna` — fuzzer de invariantes.
- `crytic/medusa` — fuzzer paralelo guiado por cobertura.
- `crytic/properties` — invariantes ERC20/ERC4626 listas para Echidna/Medusa.
- `Ackee-Blockchain/wake` — framework de testing en Python con detectores y fuzzing.

**Estado real on-chain (el corazón):**
- `fuzzland/ityfuzz` — fuzzer con estado vivo de la blockchain; arma el exploit.

**Formal (confirma matemáticamente):**
- `a16z/halmos` — bounded model checking.
- SMTChecker de `ethereum/solidity` — verificación formal dentro del compilador (`solc --model-checker`).
- `runtimeverification/kontrol` — verificación formal KEVM.
- `trailofbits/manticore` — ejecución simbólica.
- `Consensys/mythril` — ejecución simbólica sobre bytecode.

**Prueba del propio motor:**
- `Certora/gambit` — mutation testing: siembra bugs y mide si el hunter los caza.

**Inteligencia (qué buscar):**
- `Cyfrin/solodit` — base buscable de vulnerabilidades de auditorías pasadas.
- `crytic/building-secure-contracts` — catálogo de bugs reales e invariantes de referencia.

**Web (aparte, solo objetivos HTTP):**
- `projectdiscovery/nuclei` — lanza checks contra objetivos web.

---

## El mapa (pipeline por capas)

```
Objetivo (contrato + commit)
      |
  Capa 1  ESTÁTICO      Slither · Slitherin · Aderyn · 4naly3er · Semgrep
      |                 -> lista de sospechas
  Capa 2  FUZZING       Foundry · Echidna · Medusa · crytic/properties · Wake
      |                 -> intenta romper las invariantes
  Capa 3  ON-CHAIN      ityfuzz
      |                 -> exploit con estado real  (CORAZÓN)
  Capa 4  FORMAL        Halmos · SMTChecker · Kontrol · Manticore · Mythril
      |                 -> confirma o descarta
  Capa 5  INTELIGENCIA  Solodit · building-secure-contracts
      |                 -> ¿este patrón ya pasó antes?
  Capa 6  MOTOR NQC/DIABLO
                        triaje · dedup · PoC amarrada al target · severidad · firma
                        (Gambit prueba que este motor sí caza)

Web (separado):  Nuclei  -> solo objetivos HTTP
```

Regla de flujo: una sospecha solo sube de capa si la de abajo la sostiene. Un hallazgo solo es "Finding" si pasó Capa 3 (PoC real) o Capa 4 (prueba formal) y Capa 6 (amarrado al target exacto, sin duplicados).

---

## Orden de trabajo (fases)

**Fase 1 — Núcleo mínimo.** Conectar solo Capa 1 completa + ityfuzz, apuntando a UN contrato de un concurso pasado. Entregable: el pipeline corre de principio a fin sobre ese contrato y escupe una lista de sospechas + un intento de exploit.

**Fase 2 — La prueba que importa.** Correr Fase 1 contra 3 concursos cerrados de Code4rena/Sherlock sin ver el reporte. Entregable: tabla de "bugs reales encontrados / bugs totales" por concurso. Este número manda.

**Fase 3 — Según el resultado.** Si la Fase 2 encontró algo, se agregan Capa 2 y Capa 4 para subir precisión. Si encontró 0, se arregla el núcleo antes de agregar nada.

**Fase 4 — Formal e inteligencia.** Enchufar Capa 4 y Capa 5 para reducir falsos positivos y priorizar.

**Fase 5 — Medusa de confianza.** Correr Gambit sobre el motor NQC/DIABLO para probar que sí caza los bugs sembrados.

## Definición de "hecho" por fase

Cada fase se cierra solo con: la herramienta corriendo de verdad (no un adaptador sintético), evidencia de una corrida real contra un target real, y el número de la prueba ciega registrado. Sin eso, la fase sigue abierta.

## Qué NO hacer

- No agregar herramientas 21, 22, 23...
- No clonar repos "de referencia" que no ejecutan.
- No pulir custodia, huellas ni recibos antes de que la prueba ciega dé un número mayor a 0.
- No prometer "100% conectado" en ningún documento.
