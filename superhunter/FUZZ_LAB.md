# Fuzzing numérico integrado DIABLO + NQC

Este módulo ejecuta componentes originales y fijados por Git de ambos repositorios.
DIABLO aporta Target, ScopeGuard.assert_allowed y AuditLog; NQC aporta su motor
rmc016_capacity_model.solve. Los resultados se contrastan con una búsqueda
exhaustiva independiente de los componentes NQC.

**Alcance: solo oportunidades numéricas sintéticas. No es fuzzing de EVM ni una PoC,
no investiga objetivos reales ni encuentra vulnerabilidades.** Por eso la
capacidad #3 de los 50 objetivos se marca PARCIAL, nunca COMPLETA.

## Ejecutar desde la raíz de NQC

    python3 -m superhunter fuzz-lab --seed 20261103 --cases 256 --out /tmp/superhunter-fuzz-20261103
    python3 -m superhunter verify-fuzz --bundle /tmp/superhunter-fuzz-20261103
    python3 -m unittest discover -s superhunter/tests -v

Semilla uint64, 1..256 casos, salida siempre en directorio nuevo. No acepta
RPC, direcciones, PoCs ni rutas de código externos.

El generador usa SHA-256 de la pareja semilla/índice para generar de 1 a 8
oportunidades por caso: intervalos, límites de recursos compartidos, valores
enteros grandes, ceros, empates y diferentes categorías de recursos. DIABLO
autoriza cada objetivo de laboratorio antes de ejecutar NQC y registra cada
evento. Una exclusión de alcance es obligatoriamente denegada.

Cada caso exige: resultado NQC idéntico al oráculo independiente, resultado
idéntico al invertir el orden de entrada, resultado triplicado al multiplicar
por tres todos los valores (sin cambiar la selección), hash del input y
compromiso de la salida. Siete entradas inválidas deben producir ValueError.

## Verificador

El comando verify-fuzz exige COMPLETE.json con hashes, regenera todas las
entradas desde la semilla y recalcula los resultados con una nueva llamada
a NQC y al oráculo. Además comprueba los cuatro archivos originales por
identidad Git, todos los eventos de la bitácora DIABLO y su semántica, orden,
exclusión de alcance y asociación exacta al input/output.

Las pruebas negativas incluyen paquetes re-sellados, resultados numéricos
alterados, entradas falsas, registro modificado, autorización falsificada,
inconsistencias de cobertura y afirmaciones ficticias de hallazgos. Los hashes
solo prueban consistencia; no la autenticidad de un productor remoto.

## Límites

El proceso usa Python -I -B, ambiente mínimo, audit hook para red y
subprocesos y límites CPU/memoria/tamaño/timeout. NO es sandbox OS para código
hostil.

No hay Forge, Solidity, RPC, contratos externos, transacciones, explotación
ni fondos en riesgo confirmados. No se afirma 0% de falsos negativos.

Validación local ejecutada sobre el código de esta nueva entrega + baseline
de integración previo: 132 pruebas aprobadas (102 previas, 26 nuevas de fuzz,
4 nuevas de catálogo). Campaña de 256 casos con semilla 20261103 y verificación
en segundo proceso: LOCAL_FUZZ_PASS. Se requiere validación integrada posterior
del árbol remoto completo, que contiene QA/grafos añadidos en otras sesiones.
