# Reparto estable de las pruebas de SuperHunter

## Defecto corregido

El balanceo anterior por número de tests podía trasladar suites históricas
completas al añadir casos a un módulo o incorporar otro módulo. Dos regresiones
nuevas reproducen ese cambio de pertenencia con el código anterior. La rama
PR #54 tenía además un timeout histórico documentado en el worker 6.

`quality_worker.py` conserva ahora una asignación explícita de los módulos
conocidos para los ocho workers. `test_platform` pasa del worker 6 al 5 y deja
de compartir presupuesto con los estudios EVM de secuencias y semillas.
Los módulos nuevos conservan todos sus casos juntos y se asignan de forma
determinista al grupo con menos casos; no desplazan los módulos ya fijados.
Ese fallback por cantidad **no garantiza tiempos**: las nuevas suites deben
medirse y el límite puede seguir rechazando una carga excesiva.

Se conservan ocho workers secuenciales, 180 segundos de pared por worker,
90 segundos de CPU, 2 GiB de memoria virtual y 20 MiB de salida. No se borra
ningún test anterior. Cuatro regresiones obligatorias comprueban crecimiento,
módulos nuevos, separación de suites costosas y cobertura exacta sin duplicados.
El agregador y el verificador siguen comprobando inventarios, resultados y
compromisos de fuentes; no aceptan un timeout o una omisión como PASS.

## Entorno reproducible de esta validación

- Linux x86-64; Python del sistema 3.12.3 con `os.memfd_create` y
  `fcntl.F_ADD_SEALS`, en un entorno virtual independiente.
- PyYAML 6.0.3 y cryptography 46.0.4.
- Z3 C API 4.13.3.0, biblioteca SHA-256
  `7accc397d4ac387468b09489bdaff9d82bfac4ca6a7e339b8fbb2167edf9c1c0`.
- Paquete Debian `libz3-4_4.13.3-1_amd64.deb`, SHA-256
  `71383373523ef62d47eccf660cf6535c3febcbb3f88e54cb7a43124014b57359`.

Las capturas históricas ligan su motor a los bytes exactos de Z3. La misma
versión distribuida por otro proveedor puede tener otro hash y ser rechazada.
Se recuperó la biblioteca exacta; no se reescribieron capturas ni identidades.
Los primeros intentos con otro Python o motor fueron incompatibles y no se
cuentan como validaciones aprobadas.

## Comprobaciones separadas

`check` ejecuta las pruebas; `verify-check`, en un proceso distinto, vuelve a
validar el paquete de resultados contra las fuentes actuales. El segundo
comando verifica el recibo y los resultados; no vuelve a ejecutar los tests.

La comparación de bytes conserva íntegros `ci/`, `migration/` y `nqc-census/`.
El verificador histórico y sus nueve pruebas pasan sobre una copia que contiene
exactamente el ámbito de la migración original. El verificador histórico sin
adaptar rechaza el checkout ampliado por archivos raíz no contemplados en su
contrato. Por tanto este resultado **no cierra el aislamiento global**, no
verifica objetos del repositorio de origen y no recertifica NQC. No se ejecutó
la suite Rust histórica; el cambio afecta únicamente al QA Python de SuperHunter.

Los resultados de tests prueban este comportamiento local. No acreditan nuevos
hallazgos de bug bounty, severidad, precisión en terceros ni operación continua.
