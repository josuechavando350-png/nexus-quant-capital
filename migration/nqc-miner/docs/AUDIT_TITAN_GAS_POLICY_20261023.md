# Auditoría: política de gas Titan y revisión por ejecución

23 de octubre de 2026. Avance global: **43/100**, sin puntos adicionales.

Miner conservaba el antiguo presupuesto propio de MXN 2,000 como política de
planificación. La instrucción vigente del usuario exige gas de Titan. El control
actual ahora prohíbe prefondo y fallback de gas del operador, así como principal,
colateral, garantías y recurso contra el operador en cualquier activo.

La contabilidad anterior se conserva en `controls::historical_own_gas`. El cuerpo
de implementación es idéntico, separado por un módulo explícito; todas sus
pruebas siguen pasando. Sus límites históricos no se exportan como política
vigente ni se trasladan al patrocinador. No se reescribió evidencia anterior.

## Resultado implementado

`assess-gas-funding` produce un informe offline que vincula bundle, cadena,
código, bloque padre y bloque objetivo. Comprueba vigencia y revocación declaradas,
límites de gas para éxito y fallo, términos para no inclusión y ausencia de
exposición propia. Cada entrada y plan tienen digest reproducible separado por
la identidad de política. El costo de red conserva enteros uint256 y no se
convierte a cero por designar un patrocinador.

Un anuncio general, términos ausentes, simulaciones o Shadow no acreditan una
ejecución financiada. Incluso cuando los datos suministrados son consistentes,
`execution_gas_coverage_verified`, `sponsorship_authenticated`,
`spending_authorized` y `activation_allowed` permanecen en false. No existe una
integración autenticada con Titan en este incremento. La referencia de un
artefacto no comprueba su contenido, firma, disponibilidad ni pago.

## Verificación y fallos conservados

Fuente probada: `ebdee791fdc80a49aa699373dd2c1dad792073d4`.
Árbol: `a96f9e3f4cd6452dca11b4e973a32e7a5f6dcf63`.
Base previa: `075efbeeb70d593bedcc196994237c846b5df296`.

**249 pruebas Rust y 340 Python aprobadas: 589 distintas**, incluidas 15 Rust y
6 Python nuevas. No se suman repeticiones ni casos internos de property tests.
Compilación offline, Clippy con warnings denegados, formato, identidad de build,
alcance e aislamiento pasan. Se conservan 531 fuentes originales y 106 workflows
deshabilitados; hay cero workflows activos y cero cambios al observador.

La primera compilación dirigida encontró una ambigüedad de tipo en un test nuevo;
se corrigió antes del commit probado. El primer runner completo pasó Rust y los
otros controles, pero Python reportó 95 errores con 336 pruebas ejecutadas porque
el clon reducido carecía de objetos Git históricos. El resumen de ese intento
permanece con `status=fail` y conserva todos sus logs.

Se recuperaron los cinco commits exactos declarados en
`python-final/summary.json`. Una repetición quedó interrumpida por el reinicio del
entorno; no tiene resultado final y se conserva como incompleta. La siguiente
ejecución completa de Python aprobó las 340 pruebas sin omisiones. Los hashes de
todos los inputs coinciden con el primer runner. No hubo modificaciones de código
entre los controles aprobados y la repetición final. `verification.json` reúne
esos resultados y sus hashes; no presenta el intento fallido como exitoso.

La muestra CLI retenida es artificial y no contiene compromiso de Titan. Su costo
de red calculado es 18007199254740993 wei; el informe conserva el patrocinio como
desconocido. Las pruebas cubren desbordes, precisión superior a 2^53, cambios de
plan/cadena/bloque, límites de expiración, revocación, cobertura insuficiente,
pasivos propios, campos desconocidos y la imposibilidad de habilitar gasto.

## Límites y continuidad

Confianza alta en los controles probados dentro de este alcance. No se ejecutaron
nuevas consultas públicas, operaciones financieras, firmas ni despliegues. El
estado de mercado, identidad del patrocinador y compromiso por ejecución siguen
sin autenticar. Los datos de costos suministrados tampoco demuestran su propia
integridad económica ni rentabilidad.

La certificación Aave mantiene sus pendientes: cobro de deuda, validaciones y
actualizaciones iniciales, salud/eMode, mismo activo, múltiples reservas, entrada
real del Pool y preestado histórico autenticado bajo el fork correcto. La
diferencia de metadata WETH sigue abierta. El próximo bloque técnico debe retomar
esa composición; este cambio no agrega crédito de fase A, Shadow o Canary.

Reproducción: seguir `README.md` y `docs/gas-funding.md`. En clones reducidos,
recuperar primero los commits enumerados en `python-final/summary.json` mediante
`git fetch --depth 1 origin <sha>`; los auditores los leen con `git show`. Los
tests siguen siendo offline una vez preparados los objetos y dependencias.
