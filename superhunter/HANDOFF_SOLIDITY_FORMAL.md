# Continuidad — enlace solc/Z3 para controles propios

Base recuperada: SUPERHUNTER_compilacion_real_1372.zip, codigo/.
El binario recibido conserva SHA-256:
f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7.

Primero se comprobó la disponibilidad de una EVM: py-evm, eth-tester, Foundry,
geth/evm y otras bibliotecas necesarias no estaban instaladas. Los intentos de
obtener py-evm por pip y descarga fallaron; DNS no resolvía los hosts. No se
reemplazó una EVM por una máquina virtual propia ni se afirmó ejecución EVM.

Aprovechando las herramientas realmente presentes se implementó un enlace de
consultas SMT emitidas por el compilador a la biblioteca Z3 existente. La primera
prueba bloqueó correctamente ante warnings de variables no usadas en el probe
artificial de factibilidad. Se admitió exclusivamente ese warning y esas dos
ubicaciones, sin ignorar warnings desconocidos o solvers ausentes.

La aceptación nativa genera pruebas nuevas desde fuentes conocidas. Se conserva
un capture separado y etiquetado como fixture para tests unitarios de transporte.
La captura no cuenta como ejecución nueva del compilador.

No se publicaron commits, ramas o PRs; no se cambió main, workflows ni las fuentes
históricas. Los catálogos 27/50/25 no cambian de estado. El módulo 34 avanza en un
subperfil local, no en verificación universal. No se ejecuta la suite histórica
completa NQC ni el verificador global de aislamiento, pues la base es un paquete
acumulativo y no un checkout completo.

Los totales finales, huellas, resultados nativos, cambios y comprobaciones de la
copia parcheada están en VALIDATION.json fuera de codigo/. La evidencia temporal
no es autenticación del productor. El pendiente principal sigue siendo instalar
y validar una EVM local real y consolidar el acumulado en el repositorio.
