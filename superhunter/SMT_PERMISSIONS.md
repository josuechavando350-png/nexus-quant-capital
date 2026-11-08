# Z3 real para el modelo local de permisos

Esta entrega continúa **SUPERHUNTER_dominios_permisos_591.zip**. No sustituye la
rama de GitHub ni borra permisos, privacidad, regresiones, análisis estático
importado o las listas 27+50+25. El incremento es local hasta que se publique.

## Implementación ejecutada

`permission_smt.py` traduce el modelo JSON `sh-rbac-domain-v1` existente a
fórmulas QF_LIA. `smt_backend.py` es un binding original y acotado de la API C:
**invoca la biblioteca nativa Z3 instalada; no es una simulación de Z3**.
No se copiaron ni redistribuyeron sus fuentes o binarios. La validación de esta
entrega utilizó Z3 4.13.3.0, biblioteca SHA-256:
`7accc397d4ac387468b09489bdaff9d82bfac4ca6a7e339b8fbb2167edf9c1c0`.

El compilador genera identificadores numéricos, sin insertar nombres aportados
en SMT-LIB. Consulta por propiedad si existe una configuración que la viola y
si la propiedad es aplicable. Los modelos SAT se reconstruyen como asignaciones
y se comprueban con los dos evaluadores concretos existentes. También se contrasta
la respuesta con el enumerador de dominios. La compilación simbólica utiliza
recorridos de herencia propios, separados del cálculo concreto de closures.

Las discrepancias bloquean el resultado. Un caso observado por la enumeración
que contradiga UNSAT lo bloquea incluso cuando la enumeración sea parcial.
Una muestra sin fallos NO equivale a una prueba exhaustiva; la cobertura del
enumerador se conserva por separado de la decisión simbólica.

## Semántica y límites

- Todos los roles asignados están activos; la herencia es acíclica.
- Las denegaciones prevalecen, incluso si otro rol concede el permiso.
- Los usuarios deshabilitados no tienen permisos efectivos.
- Las variables alternan pertenencias directas respecto a la configuración base.
- Revocar una asignación directa no elimina necesariamente permisos heredados.
- Las reglas de separación limitan permisos simultáneos, no roles por sí mismos.

No se modelan quién puede asignar roles, sesiones, atributos, obligaciones,
políticas específicas de cloud, rutas de ataque ni alcanzabilidad temporal. No
se traduce Solidity ni se comprueba que una aplicación implemente este modelo.
Las políticas se suministran explícitamente: una especificación incorrecta puede
probar una propiedad que no corresponde al requisito real.

## Resultados

`POLICY_SMT_VIOLATION`: existe al menos un testigo SAT comprobado en el modelo.
`POLICY_SMT_PROVED`: para todas las propiedades, Z3 resolvió la negación como
UNSAT y su aplicabilidad como SAT. No hay vacuidad ni consultas pendientes.
`POLICY_SMT_INCONCLUSIVE`: faltan propiedades, hay vacuidad, UNKNOWN o NOT_RUN.
`POLICY_SMT_ERROR`: modelo, motor o evidencia inválidos; no hay aprobación.

`proved_for_declared_model` se limita a esas fórmulas y supuestos.
`independently_exhaustive_confirmed` solo puede ser verdadero si la enumeración
completa también los confirmó. No se verifica un certificado UNSAT mediante un
proof checker separado; el solver y el compilador siguen siendo parte de la base
de confianza. Nunca se declara una vulnerabilidad real o seguridad universal.

## Uso

Linux x86_64/aarch64, Python 3.11+ y una biblioteca de sistema `libz3.so.4` en
las rutas estándar explícitas del binding. Se probó Linux x86_64 con Python
3.13.5 y Z3 4.13.3.0. No se instalaron dependencias ni se probó Termux/Windows.
Si falta el motor, los comandos y sus pruebas fallan: no hay fallback ficticio.
La suite completa requiere además las dependencias anteriores del proyecto.

```bash
python3 -m superhunter check-permission-smt \
  --model /ruta/privada/model.json --out /tmp/sh-smt-001
python3 -m superhunter verify-permission-smt --bundle /tmp/sh-smt-001
```

Código 0: PROVED en el modelo; 1: VIOLATION o INCONCLUSIVE; 2: error.
`--timeout-ms` acota cada consulta (1..5000, defecto 1000).
`--resource-limit` controla unidades internas de Z3 (1..10000000, defecto 1000000).
Agotar recursos devuelve UNKNOWN, no UNSAT. Hay límite agregado de emisión de
consultas de 30 segundos; puede excederse hasta el timeout de la consulta activa.
La enumeración adicional conserva su presupuesto independiente de trabajo.

Se conservan los límites de 16 variables del modelo. Como máximo se generan
128 propiedades, 500 kB de encoding y 1 MB por consulta. No se aceptan scripts
SMT, comandos, rutas de bibliotecas, RPC ni objetivos de red como argumentos.
La biblioteca nativa es código confiado del sistema: NO está aislada por un
sandbox de seguridad. Los límites de consulta no sustituyen aislamiento de SO.

## Evidencia y conexión

Se conserva `model.json` exacto y se generan `encoding.json`, `analysis.json`,
`audit.json`, `receipt.json`, `REVIEW.md` y `COMPLETE.json`. Las consultas, hashes,
versión y hash de biblioteca quedan vinculados al modelo y al código actual.
La bitácora utiliza el AuditLog nativo de DIABLO. Las políticas y testigos son
privados; la consola y el resumen no repiten usuarios, roles ni secretos.

El verificador vuelve a compilar, evaluar los testigos, enumerar y ejecutar las
consultas determinantes SAT/UNSAT. Otro modelo SAT igualmente válido no provoca
un falso rechazo. Si una consulta determinante se vuelve UNKNOWN, la verificación
falla explícitamente. UNKNOWN/NOT_RUN registrados se comprueban como evidencia
inconclusa: no se promueven a prueba aunque hubiera más recursos posteriormente.
Los hashes identifican bytes; no son firmas de un productor externo.

El componente `permission_smt` depende de permisos, dominio, IO, privacidad y
procedencia/auditoría nativa; forma parte de QA y de los reportes conjuntos.
Las capacidades 24 y 34 y la iniciativa CERTORA.R1 permanecen parciales.
`review-platform` ejecuta sus tests reales; no analiza automáticamente políticas
externas. Para una política específica se usa el comando explícito anterior.

## Referencias de interfaz

- API C oficial: https://z3prover.github.io/api/html/group__capi.html
- Estados SAT/UNSAT/UNKNOWN: https://microsoft.github.io/z3guide/docs/logic/basiccommands/
- Parámetros: https://microsoft.github.io/z3guide/programming/Parameters/

Documentación consultada el 4 de noviembre de 2026. No se adopta una garantía
comercial ni una certificación a partir de esos documentos.
