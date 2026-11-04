# Integración nativa local — alcance exacto

Esta entrega añade ejecución real de componentes seleccionados de ambos
repositorios, no un escáner autónomo ni una reconstrucción de vulnerabilidades.
El puente Candidate/Reconstruction existente conserva su estado de revisión.

## Código original que se ejecuta

DIABLO aporta `Target`, `ScopeGuard.assert_allowed` y `AuditLog.append/verify`.
NQC aporta el solucionador de capacidad temporal RMC-016 `solve`. Sus cuatro
archivos están en `native_sources/`, idénticos byte a byte a sus blobs de origen.
`native_runtime.py` comprueba esos blobs y SHA-256 antes de cargar los mismos
bytes. No modifica las fuentes históricas ni hereda sus certificaciones.

Esto consolida las dependencias de esta integración dentro de NQC. No copia
el Hunter completo de DIABLO. El método `ScopeGuard.rate_limiter` no forma
parte del subconjunto importado; no se invoca. El código original se mantiene
intacto para conservar procedencia, no como API completa del paquete original.

## Recorrido ejecutado

`local-lab` admite únicamente cinco casos numéricos incluidos en el código.
DIABLO aplica su control de alcance local; NQC calcula los resultados; una
implementación exhaustiva separada contrasta cantidades y selecciones; DIABLO
registra la ejecución. También se comprueban una exclusión de alcance y el
rechazo de identificadores duplicados. No se lee un `PASS` suministrado por el
usuario ni se admite un booleano externo para afirmar éxito.

Los casos cubren recursos compartidos, intervalos adyacentes, desempates,
enteros superiores a la precisión de float e independencia de recursos.
Las cantidades son **fixtures sintéticos en USD-wad**, no saldos, precios,
beneficios ni pérdidas medidos en blockchain. RMC-016 resuelve capacidad:
no es un motor genérico de reconstrucción de contratos y no se presenta como tal.

## Uso desde la raíz de NQC

Requisitos del laboratorio: Python 3.11+, Linux/POSIX y PyYAML 6.0.3, que ya
estaba disponible en el entorno de validación. El laboratorio no instala nada.
El resto del puente conserva sus dependencias anteriores.

```bash
python3 -m superhunter local-lab --out /tmp/superhunter-local-001
python3 -m superhunter verify-lab --bundle /tmp/superhunter-local-001
python3 -m unittest discover -s superhunter/tests -v
```

La carpeta de salida debe ser nueva. Contiene `lab-result.json`, resultados
NQC, bitácora DIABLO, procedencia y `COMPLETE.json` con hashes. No sobrescribe
resultados previos. Los archivos usan permisos 0600 y el directorio 0700.
No se crean commits con estas salidas; deben permanecer fuera del checkout.

`LOCAL_INTEGRATION_PASS` significa que pasaron estas regresiones locales.
No implica un Finding, severidad, recompensa ni autorización de un programa.
El verificador vuelve a calcular la referencia y comprueba la cadena de hashes;
no autentica a un productor remoto ni convierte un paquete en evidencia forense
con firma independiente. Un operador con control total puede reescribir un
paquete y sus hashes: no se promete inmutabilidad física.

## Límites del proceso

El lanzador usa un intérprete aislado (`-I -B`) y no hereda claves ni URLs RPC.
El worker tiene 15 segundos de CPU, 1 GiB de espacio de direcciones, 20 MiB de
salida a archivos y 30 segundos de tiempo total controlados por el lanzador.
Un audit hook bloquea sockets y procesos secundarios, y se prueba al arrancar.
Es defensa adicional para **código propio fijado**, no un sandbox de sistema
operativo apto para ejecutar código hostil o bibliotecas nativas arbitrarias.

No existen argumentos `--target`, `--rpc`, `--poc` o `--engine`. No se ejecutan
Forge, contratos Solidity, transacciones, ataques ni búsquedas de vulnerabilidades.
Tampoco se envían reportes. No se conecta a sistemas de terceros.

## Validación de esta entrega

Se reprodujo el baseline de 67 pruebas. La suite ampliada ejecutó **102 pruebas,
0 fallos, 0 errores y 0 omisiones** en Python 3.13.5 con PyYAML 6.0.3.
Incluye llamadas efectivas a las funciones nativas, comparación numérica
independiente, evidencia alterada, desacuerdos, truncado de bitácora, timeouts,
rechazo de parámetros externos, errores del worker y no sobrescritura.
Además se ejecutaron por CLI los cinco casos y su verificación en otro proceso.

La primera configuración del worker de 256 MiB de espacio de direcciones falló
con MemoryError porque el intérprete del entorno ya usaba más memoria virtual.
Se ajustó el límite a 1 GiB y se volvieron a ejecutar las pruebas. No se omitió
ningún test para ocultar ese error.

No se ejecutó la suite histórica completa de NQC ni su verificador de aislamiento:
no hay checkout completo disponible en este entorno. La revisión de preservación
se limita a hashes y diff remoto; solo cambia `superhunter/`. No hay ejecución
GitHub Actions, evidencia de bugs reales ni integración operativa del Hunter
completo. Los archivos VALIDATION.md y validation-results.json previos se
conservan como registros de la entrega anterior, no como resultados de esta.
