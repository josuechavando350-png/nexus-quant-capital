# Comprobaciones conectadas — alcance y evidencia

## Qué se implementó

El comando `system-check` conecta los componentes locales que realmente existen:
DIABLO controla el alcance, NQC calcula capacidad, una referencia independiente
contrasta el cálculo, DIABLO registra los eventos y un verificador comprueba
sus enlaces. El resultado también incluye una comprobación exhaustiva finita
y el estado de los 50 requisitos. No implementa los motores pendientes.

```bash
python3 -m superhunter system-check --out /tmp/superhunter-system-001
python3 -m superhunter verify-system --bundle /tmp/superhunter-system-001
python3 -m unittest discover -s superhunter/tests -v
```

La carpeta debe ser nueva. El worker sigue sin admitir objetivos, RPC, PoCs,
motores externos o código de usuario. No hay despliegues ni acciones en terceros.

## Brecha que se reprodujo y corrigió

En el baseline `665728368468988204d43cbfb7c06f2c8502059f`, el verificador local
comprobaba hashes y resultados, pero no toda la semántica de los eventos. Una
bitácora sintética cuyo evento de alcance decía DENY podía coexistir con un
resultado satisfactorio después de recalcular sus hashes. Se reprodujo ese
caso exclusivamente sobre el propio laboratorio antes de modificarlo.

Ahora cada evento debe corresponder al caso, entrada, resultado y referencia
correctos. Un DENY no acredita un cálculo autorizado, ni un input de un caso
acredita el resultado de otro. Se comprueban tipos exactos, tiempos y el esquema
completo del resultado NQC. También se registra el rechazo esperado de duplicados.

`evidence-graph.json` contiene 30 nodos vinculados: procedencia, autorizaciones,
entradas, NQC, referencias, comparaciones, controles negativos, bitácora y veredicto.
El verificador vuelve a construir el grafo desde los artefactos comprobados; no
confía en dependencias o hashes declarados en el propio grafo.

## Qué significa la comprobación exhaustiva

`bounded_capacity.py` enumera **1,728 casos**: tres registros etiquetados,
tres intervalos posibles, dos valores y dos cantidades, con un recurso de
capacidad dos. Cada caso se ejecuta en el solucionador original de NQC y se
contrasta con una implementación separada que enumera sus ocho subconjuntos.
Son **13,824 evaluaciones de subconjuntos** en la referencia, no transacciones.

Hay cobertura completa de ese dominio declarado. No es verificación formal
universal, prueba de ausencia de vulnerabilidades, benchmark de Solidity ni
cálculo de fondos robables. Los números son sintéticos y adimensionales; el
campo USD-wad del módulo histórico se conserva por compatibilidad.

La verificación posterior vuelve a calcular el transcript usando únicamente la
referencia: no invoca el solucionador NQC. El certificado incluye el dominio,
conteo, hashes de fuentes y el resultado agregado. Si falta un caso o cambia el
código relevante, no conserva una acreditación anterior.

## Los 50 requisitos, sin palomitas inventadas

`capabilities.json` enumera los 50 IDs, dependencias, referencias reales de código,
criterios de aceptación y límites defensivos. Un validador exige cobertura 1..50,
sin duplicados, ciclos ni referencias a módulos inexistentes.

Estado: **32 pendientes, 3 bases parciales y 15 que requieren rediseño defensivo**.
Las bases parciales son 37 (revisión de impacto declarado), 45 (worker aislado)
y 47 (borrador Markdown). Ninguna de las 50 capacidades completas se acredita
como implementada. Un registro no se convierte en implementación por existir.

Los rediseños sustituyen explotación autónoma, evasión o extracción de secretos
por validaciones defensivas y regresiones delimitadas. No se incorporan motores
de RCE, evasión de sandboxes/WAF/captchas ni extracción de credenciales.

`CHECKLIST.md` se genera junto con la ejecución y se contrasta durante la
verificación. No admite palomitas añadidas que contradigan el registro verificado.
La base de integración se lista separadamente de las 50 capacidades solicitadas.

## Validación ejecutada

Baseline reproducido: **102 pruebas**. Suite ampliada: **146 pruebas, cero fallos,
cero errores y cero omisiones**. Se añadieron 44 regresiones; las anteriores se
conservan. La comprobación del conteo de eventos pasó de 18 a 24 porque ahora
se registran cinco referencias y el rechazo de duplicados, no para omitir controles.

Se ejecutaron `system-check` y `verify-system` en procesos distintos. Además,
los tests impiden sockets y ejecución de procesos dentro del circuito en memoria.
El launcher conserva su worker fijo y sus límites. No es un sandbox de sistema
operativo apto para ejecutar código hostil.

## Límites de confianza

El grafo evita contradicciones y vínculos incorrectos; no autentica a un productor
remoto. Quien controle todo el equipo puede reescribir un paquete coherente y sus
hashes. No se afirma inmutabilidad física ni prueba criptográfica de ejecución.

`LOCAL_DEFENSIVE_CHECKS_PASS` no significa vulnerabilidad, recompensa ni Hunter
terminado. No se ejecutaron Forge, contratos Solidity, RPC, escáneres ni envíos.
No se ejecutó CI, la suite histórica completa de NQC o el verificador de aislamiento
completo: solo se materializó el subárbol de SUPERHUNTER. La preservación del resto
se comprueba mediante diff y hashes de árboles del repositorio.

La evidencia local usa schema_version=2 y exige el grafo nuevo; los paquetes del
laboratorio anterior no se elevan silenciosamente al nuevo nivel de verificación.
Los adaptadores Candidate/Reconstruction continúan en REVIEW_REQUIRED.
