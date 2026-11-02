# Shadow acumulado · 14 corridas en vivo, 28.8 h

> Solo lectura. No se firmó ni se envió nada. «A tiempo» quiere decir que, con lo que tardamos en decidir y 20 ms supuestos de red (ver el trozo y enviar desde un servidor cerca del secuenciador; no se mide), nuestra transacción habría llegado antes de que se publicara el trozo del ganador. Es una cota optimista: el trozo se cierra un poco antes de publicarse, y dentro del trozo gana la propina más alta, que aquí no entra.

- Liquidaciones reales vistas: 7 ($197 de bono), 5 directas.
- Peleables (el ganador reaccionó en un trozo posterior al de la actualización del oráculo): 2 ($0).
- Con la ventana medida por WebSocket: 1; mediana 0 ms, mín 0 ms, máx 0 ms.
- Con bono de $1 o más: 0; en el escenario aproximado habríamos llegado a tiempo para el trozo del ganador en 0 ($0 de $0).
- Muestra: 0 de 20 casos con evento único, trozos medidos y tiempos con origen común; faltan 20. Estado: INSUFICIENTE.
- En esa muestra, holgura estimada positiva en 0. El envío sigue siendo supuesto.
- La mediana de una corrida y la clasificación inferida por propinas no cuentan para la meta. Veinte observaciones solo abren una revisión: no certifican captura, inclusión ni rentabilidad.
- Calidad: 0 eventos duplicados omitidos; 0 conflictos; 0 líneas inválidas. Los archivos de entrada quedan identificados por SHA-256.
- La vía rápida vio cruzar la posición antes que el ganador la liquidara en 2 casos; holgura positiva en 0 (mediana -19 ms).
- Rivales: en 2 de 5 liquidaciones otro bot lo intentó y perdió; el segundo perdió por llegar tarde en 2 y por pagar menos en el mismo trozo en 0.

| Mercado | Bono | Ventana | Decidir | Holgura (est.) | Origen |
|---|---|---|---|---|---|
| cbETH/USDC lltv 77.0% | $0 | 0.3 ms | 0.9 ms | -20.6 ms | hash_y_mediana |

Corridas: 40148465482 (0.1 h, 0 liq.), 40149648096 (0.3 h, 0 liq.), 40150803367 (0.3 h, 0 liq.), 40159762831 (0.2 h, 0 liq.), 40160515156 (0.3 h, 0 liq.), 40161609659 (0.2 h, 0 liq.), 40162401105 (0.2 h, 0 liq.), 40163135976 (2.2 h, 1 liq.), 40171040689 (1.4 h, 0 liq.), 40176606411 (3.3 h, 1 liq.), 40190198885 (3.7 h, 0 liq.), 40207318890 (5.5 h, 0 liq.), 40349833440 (5.5 h, 4 liq.), 41376606202 (5.5 h, 1 liq.).
