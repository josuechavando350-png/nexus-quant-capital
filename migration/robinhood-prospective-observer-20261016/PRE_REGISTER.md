# Protocolo del piloto fijado antes de observar sus resultados

Esta versión estudia un solo mercado Morpho de Robinhood y la ruta wsNET/NET/USDG
ya reproducida. La elección del mercado procede de investigación histórica;
la cohorte nueva se selecciona exclusivamente por eventos Borrow de los últimos
2048 bloques respecto de una cabecera aún por consultar. No representa todos
los prestatarios ni toda la red. No se amplía la ventana si salen pocos casos.

La selección incluye todas las direcciones onBehalf distintas, hasta ocho.
Exceder ocho direcciones, 64 eventos o 16 bloques con eventos detiene el piloto;
no se recorta una muestra después de conocer su salud. Cada bloque de eventos
se contrasta con su cabecera y el ancla se confirma antes de congelar la cohorte.

Después de congelarla se observan tres cabeceras nuevas. Las lecturas de mercado,
oracle, tasa y posiciones se fijan por hash con requireCanonical. El criterio
incluye deuda positiva y margen de salud de hasta 100 puntos básicos. Se registran
todos los descartes, incluso falta de capacidad, ausencia de deuda y periodos sin
señal en una cohorte no vacía. Una cohorte vacía no demuestra ausencia de oportunidades.

Se simulan como máximo dos candidatos por ronda, por orden ascendente de dirección.
El tamaño es un cuarto del colateral, limitado por deuda y por 250 USDG de repago;
una regla fija de división por dos corrige hasta ocho veces el redondeo. El mínimo
de excedente es 2 USDG. Son parámetros de investigación, no tamaños optimizados.

Cada candidato preparado se registra antes de simular. Se prueba el estado
observado y una hipótesis temporal +1 segundo con el mismo estado. Solo se
provisionan efímeramente tres fixtures propias; no se cambia el protocolo ni
ArbSys. Las direcciones de fixtures deben carecer de código en el ancla. Los
runtime Morpho/oracle/IRM deben coincidir con el testigo histórico autenticado.

Se conserva la transacción preparada para contrastarla con la siguiente cabecera
observada. No se actualiza su deadline de bloque. Si hay bloques intermedios sin
observar y ya venció, su supervivencia intermedia queda desconocida. Los últimos
candidatos quedan censurados al terminar el piloto, sin adjudicarles éxito o fallo.

Las consultas son secuenciales en esta primera medición. Se guardan inicio y fin
monotónicos de cada RPC, llegada de cabecera, disponibilidad de insumos, fin de
simulación y decisión. Un presupuesto hipotético de 1000 ms marca decisiones
viejas. No mide por sí mismo latencia del secuenciador, admisión ni inclusión.

El programa termina al completar tres rondas, al superar 90 consultas/240 segundos
o ante error de transporte/proveedor. No reintenta, cambia de endpoint, abre
suscripciones ni se mantiene como servicio. Usa el endpoint público de ejemplo
documentado por QuickNode. El preflight previo tuvo solo dos lecturas y no
consultó prestatarios, resultados de liquidación ni estado económico del mercado.

Las simulaciones prospectivas cubren la ruta directa, sin cuenta abstracta,
paymaster ni bundler. Su tarifa no se presentará como coste del ciclo completo.
La sensibilidad económica usa supuestos congelados en policy.json y el prefund
histórico conservador para éxito/fallo; no son cotizaciones ni tasa de captura.
Financiación acreditada: cero. Admisión, latencia viable y costes completos:
no acreditados. Ninguna salida autoriza operar.

Fuentes: código Morpho fijado en 8e26ca6a8dbc5089edcd67fb576248810fd2870a;
runtime/route de PR8 y PR10; criterios de cohortes de los observadores archivados
de NQC. Los archivos archivados se preservan sin modificación. Los hashes de la
implementación y política se guardan en registration-sources.json y el commit
se publica antes de iniciar el piloto. El diario local encadena hashes, pero no
constituye una fuente de hora independiente ni prueba criptográfica del estado EVM.
