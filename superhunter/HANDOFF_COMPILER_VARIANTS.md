# Continuidad — diferencial de configuraciones del compilador

Base exacta: SUPERHUNTER_revision_nativa_1643.zip, subcarpeta codigo/.
SHA-256 de la base: `0f00349d278e6ab4d7bf6147f3c6dfed8142475dd2596f5131f2c1f15ac22b12`.

La base se reejecutó: 1,643 pruebas. Se añade un perfil de comprobación de
configuraciones de compilación, sin cambiar ninguno de los motores originales
ni los archivos anteriores de tests. Los resultados de esta entrega deben
consultarse en VALIDATION.json y en los logs reales del paquete, no inferirse
de este archivo o de cifras históricas.

El nuevo módulo depende de una aceptación nativa aprobada por la misma versión.
Su comprobación reejecuta las herramientas para el perfil original y añade dos
perfiles fijos optimizados. No ofrece fuentes, contratos o secuencias externas.
Es un laboratorio diferencial de controles conocidos, no un motor autónomo
de descubrimiento ni un verificador de equivalencia universal.

Los catálogos 27/50/25 y las cinco fuentes nativas se preservan. El motor de
compilación, workers, modelos formales, EVM, conciliador y orquestador anterior
no se modifican: la ruta adicional los invoca y exige su evidencia verificable.
El código completo está en codigo/. El parche es incremental contra ZIP1643,
no contra una rama remota que tenga solo parte del acumulado.

Siguen pendientes: consolidación remota de todas las entregas; conectores
activos; benchmark ciego; descubrimiento original. No afirmar un porcentaje
de capacidad o superioridad a partir del número de tests. No crear cuentas,
suscripciones, workflows, envíos de reportes ni transacciones. No tocar Cano,
Vercel, otros repositorios, main ni las fuentes históricas NQC.

Solo se dispone del paquete acumulativo, no un checkout histórico completo.
No se ejecuta por ello la suite histórica NQC ni su verificador global de
aislamiento; la comparación de archivos del paquete no los sustituye.
