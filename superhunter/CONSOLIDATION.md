# Conciliación de entregas — 4 de noviembre de 2026

## Procedencia

Base de aplicación: PR 35 en `adc28a062668de996848ace5d233d2fa055fbd4c`.
Su identidad ejecutable/políticas fue reconstruida desde los archivos
recuperados y coincidió exactamente con
`c292801202c0548b7ba4f364fe80848e427e14ae4bd8fd786d015f851ea7ed7d`.
La suite base de 251 pruebas se volvió a ejecutar, sin fallos ni omisiones.

Se incorporó PR 37, commit `42dc168efd63e7ac3a8919635773ed66ddb2758c`,
cuya suite archivada de 261 pruebas también se volvió a ejecutar. Además se
integró el paquete local de privacidad/regresiones entregado anteriormente;
su SHA-256 y la unión de 364 IDs previos están en `reconciliation-origins.json`.
No se declara que esos cambios ya hayan sido publicados en GitHub.

## Resolución de conflictos

Se unieron las entradas de CLI y las asignaciones de módulos, dependencias y
tests obligatorios en QA. Se mantuvieron los verificadores de grafos y campañas
numéricas, incluida la comparación canónica que distingue booleanos de números.
Se conservaron los reportes portátiles, las funciones de privacidad y el
comparador de regresiones. Ningún test previo fue eliminado.

Los dos catálogos de 27 puntos ya no se editan independientemente. La vista
legacy es una proyección comprobada del registro rector y admite PARTIAL.
Se conservaron unidas las referencias de pruebas de ambas ramas. Las 50
capacidades continúan separadas, sin subir artificialmente su estado.

Los ajustes de tests existentes son explícitos: el conteo del catálogo pasa
al estado real de cinco parciales; el reporte distingue tres hitos parciales;
los recibos sintéticos de los tests de revisión incluyen las nuevas suites;
y una prueba de falta de test aísla ese gate de la nueva comprobación de
proyección. No se quitaron aserciones para presentar un hallazgo como confirmado.

## Pruebas nuevas

16 tests cubren continuidad de IDs, registro completo de módulos, proyección
de checklists, rechazo de estados divergentes, conservación de referencias,
reportes HTML ligados a evidencia, privacidad de textos sin modificar el
original y diagnóstico sin eco de argumentos en las rutas reunidas.

En la primera prueba conjunta se observó un conteo viejo (4 parciales en vez
de 5); se corrigió usando la aserción ya existente en el parche de privacidad.
El primer arranque aislado de los nuevos fixtures carecía de inicialización
de clase; se corrigió. Dos invocaciones directas largas fueron interrumpidas
por el límite del entorno; la ejecución completa mediante el worker concluyó
y su recibo registra todos los resultados. No se omitió ningún test.

## Límites

La revisión conjunta ejecuta código propio y datos numéricos sintéticos. No
conecta un flujo de explotación autónoma ni demuestra nuevos bugs. No se
promueve un hash a autenticación de productor ni una suite finita a ausencia
de falsos negativos. El punto 29 y el 48 siguen parciales.

No se descargó el repositorio histórico entero; el alcance de materialización
fue el paquete SUPERHUNTER. No se ejecutó su verificador histórico completo de
importación ni todas las suites Rust/Python de Census. El parche solo modifica
`superhunter/`; los módulos nativos importados permanecen byte a byte.
