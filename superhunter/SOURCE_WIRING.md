# Enlaces reales de código: revisión estática de imports

`source_graph.py` lee y analiza el AST de los archivos Python del propio paquete.
No ejecuta su contenido ni importa módulos analizados. El grafo anterior de
componentes es una declaración de arquitectura; este componente lo complementa
con referencias extraídas directamente de archivos, líneas y hashes.

## Comandos

```bash
python3 -m superhunter audit-wiring --out /ruta/privada/caso-nuevo
python3 -m superhunter verify-wiring --bundle /ruta/privada/caso-nuevo
```

El código 0 indica sintaxis de imports resuelta dentro del perfil; 1 significa
que hay referencias sin resolver o carga dinámica que requiere revisión; 2
significa que la entrada, ejecución o evidencia es inválida. Ninguno garantiza
que todo se ejecute, que esté autorizado un objetivo o que el software sea seguro.

Se detectan imports relativos/absolutos, inicializadores de paquetes, imports
dentro de funciones y condiciones, paquetes namespace, referencias externas y
ciertas formas de carga dinámica. Se calcula el cierre de imports desde
`__main__`; NO es un grafo de llamadas, una prueba de alcanzabilidad de una
vulnerabilidad ni un análisis de dependencias vulnerables. Las ramas muertas
se conservan como sintaxis. Alias dinámicos, reflexión y subprocesses pueden
crear enlaces que el análisis no resuelve. El JSON expone esa incertidumbre.

Los nombres importados pueden ser atributos en lugar de módulos. Los atributos
no resueltos se señalan sin afirmar que el código necesariamente está roto.
Los ciclos de imports se recorren sin bucles infinitos: no se consideran por sí
solos vulnerabilidades. La detección de ciclos inválidos de la arquitectura
sigue perteneciendo al gate de componentes existente.

Se conservan los hashes de cada archivo y la ubicación de cada enlace. El
verificador recalcula el grafo a partir del código actual: una fuente cambiada,
un reporte alterado o una afirmación `all_runtime_links_proven=true` no puede
aprobarse por recalcular solamente el manifiesto. No hay firma de productor ni
certificación externa. El paquete de evidencia debe permanecer privado.

## Integración y alcance de esta entrega

CLI → lectura de fuentes → AST → grafo/pendientes → QA → reporte conjunto.
En la versión local acumulativa, `review-platform` añade `source_wiring` a sus
hechos comprobados y cuenta sus referencias en el resumen. En la variante de
publicación sobre PR38, `review` añade el mismo grafo a `review.json`.
La suite registra un componente específico y exige controles negativos.

El análisis identificó en las copias nativas la referencia
`native_sources/diablo/scope.py → ratelimit`, no incluida en el subconjunto
importado. Una llamada local a `ScopeGuard.rate_limiter()` confirmó
`ModuleNotFoundError`. Esto ya era una API no soportada del subconjunto; no se
presenta como una vulnerabilidad nueva ni como un problema de un tercero.
Los componentes de laboratorio no invocan ese método. Se conserva visible el
pendiente en lugar de modificar las fuentes históricas para simular conexión.
La carga de fuentes verificadas mediante `exec` en `native_runtime.py` también
se registra como dinámica; no se inventan enlaces para convertir el grafo en PASS.

Slither/solc no están instalados; en esta sesión fallaron DNS/descargas oficiales.
No se ejecutó ni simuló una compilación Solidity. No se añadieron escáneres de
objetivos externos, RPC, generación de exploits, evasión ni envío de reportes.
Esta unidad no completa SlithIR, taint, los motores Hunter ni los 27/50/25 planes.

## Reproducción

Usar un entorno Python 3.11+ limpio con la dependencia ya fijada PyYAML 6.0.3.
Se ejecutó Python 3.13.5; se creó un venv sin pip y se reutilizaron los bytes de
PyYAML 6.0.3 ya instalados. No se descargaron herramientas ni se cambió el
intérprete del usuario. Los recibos de la entrega registran las versiones y
resultados reales; no heredar los contadores de validaciones anteriores.

```bash
python3 -m unittest discover -s superhunter/tests -v
python3 -m superhunter review-platform --out /ruta/privada/revision-nueva
python3 -m superhunter verify-platform --bundle /ruta/privada/revision-nueva
```

La variante remota focalizada conserva los comandos de su base PR38; no incluye
el acumulado local completo. No sustituir la entrega local por esa rama reducida.
