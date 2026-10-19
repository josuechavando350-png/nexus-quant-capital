# Política determinista de selección v1

**Prioridad de investigación ≠ rentabilidad ≠ probabilidad de captura.**
No hay puntuación ponderada, probabilidades entrenadas ni precios supuestos.

Tres salidas independientes por candidato:

1. **A — Evidencia para estudiar:** libro de caja parcial; evento y gas de indexador;
   o evento solamente. Integridad de archivo y autenticación on-chain son campos distintos.
2. **B — Indicio económico:** cota superior histórica identificada o margen desconocido.
   Un colateral/deuda grandes o una liquidación exitosa no justifican beneficio neto.
3. **C — Adquisición pendiente:** familias de requisitos, decisión que resolverían,
   posibilidad limitada de reutilizar trabajo y carga estructural; dinero, horas,
   peticiones y disponibilidad permanecen desconocidos.

Los nueve criterios de cada `assessment.criteria` son: fuentes, reconstrucción,
venta, margen, financiación del principal, gas/obligaciones, competencia, carga de
evidencia y refutación rápida. No se suman valores desconocidos como ceros.
En esta muestra la mayoría de esas dimensiones no permite discriminar: siguen
bloqueadas para todos. El motor deja visible esa falta de información.

## Orden operativo

1. Rechazar hashes/identidades inconsistentes, conflictos de duplicación y unidades
   incompatibles. No ordenar expedientes corruptos como si fueran candidatos pobres.
2. Separar los escenarios cerrados por cota no positiva. No extender un descarte a
   toda una transacción, mercado o familia fuera de sus condiciones.
3. Congelar las referencias cuyo análisis disponible ya está agotado (B). Reabrirlas
   requeriría otra fuente, vinculada por hashes, que resuelva una incertidumbre.
4. Mantener el nivel documental de A/B separado de la lista de adquisición.
   Ninguno satisface una admisión económica.
5. Para una **propuesta diagnóstica** entre los restantes, ordenar por:
   - menor número reportado de transacciones ordinarias anteriores;
   - deuda con denominación comparable al gas nativo bajo las condiciones del
     adaptador (en este conjunto, WETH/ETH, nunca equivalencia por símbolo);
   - disponibilidad de observaciones financieras de gas;
   - identificador canónico solo para presentación estable de empates.

Los empates sustantivos se conservan como tales. La prioridad no usa el tamaño del
colateral, un supuesto precio USD ni una frecuencia estimada. El índice reportado
debe autenticarse antes de aprovecharlo. La decisión no incorpora una estimación
de coste de proveedor ni de tiempo, porque no existen. El fallo histórico de acceso
queda visible y no equivale a permiso de reintento.

Estados disponibles: `VALE_LA_PENA_INVESTIGAR` para un expediente no congelado con
indicio acotable; `REQUIERE_EVIDENCIA_ESPECIFICA`; `NO_PUEDE_EVALUARSE_CON_DATOS_ACTUALES`;
`DESCARTADO_DENTRO_DE_CONDICIONES`. **En los datos presentes ningún nuevo candidato
recibe el primer estado.** La propuesta de adquisición no cambia su clasificación
económica. Ningún estado activa admisión comercial.

## Motor monetario

Toda cantidad tiene cadena, identificador de activo y escala decimal. Se utilizan
enteros exactos; se rechazan floats, exponentes, truncamientos y sumas de activos
distintos. La conversión de la obligación WETH de B a ETH es explícita, específica
de su ruta archivada; no habilita convertir pufETH, ezETH o stablecoins a ETH/USD.

Para venta `S=[s_min,s_max]` y obligaciones `C_i=[c_min,c_max]`:

- Cota superior neta: `s_max − sum(c_min)`.
- Cota inferior neta: `s_min − sum(c_max)`.
- Si falta un extremo necesario, el resultado correspondiente es `null`.

Una obligación desconocida no negativa puede tener cota inferior matemática cero
y superior sin acotar. Eso **no estima su coste real en cero**: deja la cota inferior
del neto sin determinar. No se admiten reintegros negativos inventados. Todas las
conclusiones delimitan qué ingresos y obligaciones incluye el expediente.

Deuda/principal repagado, prima de financiación, gas, inclusión, fallos, operaciones
y otras obligaciones son categorías distintas y obligatorias. Préstamos recibidos
no son ventas ni beneficios. Colateral sin venta/valoración válida no es ingreso
líquido comparable. Comisiones/impacto ya incluidos en la venta no se descuentan
de nuevo. Los componentes cubiertos impiden sumar otra vez el tip dentro del gas.

Una cota positiva, incluso bajo hipótesis explícitas, nunca se transforma en P&L
capturado. Las pruebas de intervalos sintéticos no son estrategias ni datos de
mercado. El kernel no ejecuta operaciones ni autentica una cadena.

## Criterio de valor informativo

Se prioriza una decisión potencial antes de un replay costoso: poder **refutar**
la contabilidad de una ruta con recibo/traza o identificar exactamente su residuo
y obligaciones desconocidas. Si la evidencia de orden desmiente el índice cero,
debe recalcularse la prioridad. Si nunca se consigue la evidencia, el candidato
permanece suspendido; el radar no rellena ese hueco con una etiqueta de éxito.

No hay modelo estadístico propuesto ni entrenado. Para estimar probabilidades
en el futuro harían falta observaciones predecisión con cobertura conocida,
competidores, latencias, costes de intentos incluidos/no incluidos y ventanas
temporales fuera de muestra. Las etiquetas actuales no permiten ese entrenamiento.
