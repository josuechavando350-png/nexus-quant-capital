# Reparación del enlace nativo de admisión local

Se recuperó `nexus-offensive/core/ratelimit.py` del repositorio DIABLO, commit
`0c27792fba1af1f925bfff03fbcc6fd82a3791b0`. Se conserva exactamente el blob
`ab5dc6292f4837376ee6f0849377f560839e5a99` (3554 bytes). Las cuatro fuentes
nativas anteriores no fueron modificadas. El cargador ahora verifica cinco
fuentes y precarga el limitador antes de permitir su importación relativa.

## Reparación comprobada

El mismo comando ejecutado en la base anterior producía `ModuleNotFoundError`
al llamar `ScopeGuard.rate_limiter()`. En esta versión crea el limitador nativo;
con capacidad uno y reloj fijo admite una operación y aplaza la segunda.
El analizador de imports ya no declara ausente `diablo.ratelimit`. La carga por
`exec` de las fuentes fijadas sigue siendo dinámica: no se declara conectividad
universal en ejecución ni seguridad absoluta del intérprete.

El módulo original es histórico y no valida todos sus parámetros. El nuevo
`rate_control.ScopedRateLimiter` proporciona una interfaz local que rechaza
cantidades de tokens negativas, cero, booleanos o números no finitos; límites
inválidos; relojes inválidos o que retroceden; y cambios de configuración.
También normaliza los nombres antes de consumir tokens, para que sus variantes
con mayúsculas/punto final no obtengan créditos distintos. Las excepciones
públicas usan códigos fijos y no repiten valores suministrados.

El limitador es **por clave normalizada**, no un límite global entre todos los
hosts, ni un servicio distribuido. Solo expone admisión no bloqueante: no
programa tareas, duerme, envía peticiones, ejecuta callbacks ni concede permisos
de red. El ScopeGuard existente no sustituye la política cadena/contrato de
Program Intelligence; esta integración es exclusivamente de controles locales.

## Conexión con NQC y evidencia

Los cinco casos propios de `local-lab` pasan ahora por la comprobación de alcance
y la admisión antes de invocar `RMC016.solve`. Cuando la admisión se aplaza, el
solver NO se ejecuta. El reporte registra las admisiones y la procedencia de la
quinta fuente; los verificadores comprueban las nuevas identidades y rechazan
contradicciones. El grafo causal mantiene sus 24 nodos y registra la quinta
fuente en su testigo de procedencia. Esto no añade una prueba criptográfica de
que un productor remoto haya ejecutado el código: siguen aplicando los límites
de custodia y verificación existentes.

El reloj cero del laboratorio es deliberadamente fijo y evita retrasos en los
fixtures numéricos. No pretende medir tráfico o duración en una red real. Las
pruebas de frontera de recarga, concurrencia y límite de claves se ejecutan
separadamente. La interfaz usa `time.monotonic` por defecto fuera del fixture.

## Pruebas nuevas y compatibilidad

Se añaden 32 tests. Incluyen 64 intentos con ocho hilos y capacidad tres, así como
512 decisiones contrastadas con una referencia independiente que usa fracciones
exactas. No se elimina ninguna prueba anterior. Se actualizan las expectativas
exactas de cinco fuentes y el rechazo de cuatro fuentes incompletas. El test
histórico de dependencia ausente conserva su ID y comprueba ambos casos:
la instalación actual está resuelta; quitar el archivo sigue siendo detectado.

Los paquetes anteriores conservan sus archivos intactos, pero su procedencia
con cuatro fuentes ya no acredita esta versión de cinco. Deben verificarse con
su versión original o regenerarse con esta versión, no cambiar sus manifiestos
a mano. Los estados de los catálogos 27/50/25 no se promueven por este arreglo.

## Reproducción

```bash
python3 -m unittest discover -s superhunter/tests -p test_rate_control.py -v
python3 -m superhunter local-lab --out /ruta/privada/ejecucion-nueva
python3 -m superhunter verify-lab --bundle /ruta/privada/ejecucion-nueva
python3 -m superhunter audit-wiring --out /ruta/privada/enlaces-nuevos
```

`audit-wiring` puede devolver revisión pendiente por la carga dinámica aunque
la dependencia faltante esté resuelta. Un limitador no bloquea toda evasión
posible ni actúa como sandbox para código hostil. No se ejecutaron compiladores
Solidity, EVM, escáneres, transacciones ni objetivos externos en esta entrega.

## Revalidación de conexiones sin repetición innecesaria

La revisión completa vuelve a analizar el mismo paquete muchas veces. Se añadió
una caché de UNA entrada: requiere igualdad exacta del inventario y de todos los
bytes, además de la misma función analizadora. Cada llamada captura las fuentes
antes y después, también cuando acierta la caché. No usa fecha de modificación
como evidencia ni devuelve un objeto mutable compartido. Seis pruebas adicionales
comprueban reutilización, cambio de bytes, cambio durante lectura, contaminación
del resultado devuelto, error de análisis y sustitución del analizador.

Esta optimización no cambia el significado del grafo ni promete rendimiento
universal. Reduce trabajo repetido dentro de un proceso; no es almacenamiento
persistente ni autenticación del productor.

## Ejecución completa mediante particiones verificadas

El límite monolítico de QA resultó insuficiente para esta suite y dejó intentos
incompletos registrados. Se reemplazó por cuatro particiones deterministas de
módulos completos. Las fuentes y el inventario global deben coincidir en los
cuatro workers. La unión debe contener exactamente todos los tests, sin duplicar
ni omitir ninguno. Fallos, skips, errores y éxitos inesperados se preservan y
bloquean la aprobación. Diez pruebas nuevas ejercitan estos controles.

Los límites por worker siguen en 90 segundos de CPU y 180 de tiempo real; son
cuatro workers secuenciales, no una promesa de terminar dentro del presupuesto
monolítico anterior. No se alteraron los límites internos de las pruebas.
La evidencia conjunta conserva los cuatro recibos, sus fuentes y sus IDs;
verify-check vuelve a comprobar la agregación. No autentica productores remotos.
