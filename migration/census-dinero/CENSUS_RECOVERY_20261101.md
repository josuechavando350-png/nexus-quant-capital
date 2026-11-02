# Recuperación acotada del Census mientras Shadow v11 observa

La corrida Shadow `41376606202`, productor `524092ae8f3e5da19bc0f7fa7f707f3068603401`,
sigue independiente. Su configuración se conserva en `runs/shadow-v11.json`.
Este incremento solo cambia la configuración de una nueva corrida Census; no cambia código.

En la corrida histórica `40215984099`, cuatro tramos fallaron antes de recolectar eventos:

| Cadena | Timestamp finalizado observado | Fin solicitado | Diferencia |
|---|---:|---:|---:|
| Scroll | 1792940441 | 1792944000 | 3559 s |
| Linea | 1792942838 | 1792944000 | 1162 s |
| Lisk | 1792930833 | 1792944000 | 13167 s |
| Abstract | 1792859198 | 1792944000 | 84802 s |

Fuente: los `meta.json` y `log.txt` correspondientes bajo
`census-dinero/resultados@e0c6c4bd5c2ee852cb84de72e4a572febc140033/corridas/40215984099/`.
Estos son motivos históricos, no un diagnóstico de la disponibilidad actual de sus RPC.

Se reintentan solamente esos cuatro tramos, con `end_utc` fijado en
`2026-10-25T16:00:00Z`, inicio `2026-09-25T16:00:00Z`, Morpho y presupuesto de
recolección de 20 minutos por cadena. Se preserva la guarda de finalización y la
ventana completa: no se recorta el período para declarar éxito. La recuperación puede
encontrar otros bloqueos, por ejemplo datos históricos podados; debe conservarlos.

`solo` selecciona los cuatro trabajos. `incluir_corridas=[40215984099]` permite al
informe integrar los otros tramos preservados sin volver a recolectarlos. Un trabajo
concluido no implica cobertura completa: revisar `events_complete`, `time_budget_hit`,
`fatal_error`, errores de valoración y conciliación del informe final.

El commit empieza por `Census`, por lo que usa el grupo de concurrencia Census del
workflow existente. Shadow usa otro grupo y conserva su propio commit fijado. No se
agregan workflows, permisos, fondos ni envíos de transacciones. El presupuesto de
recolección no sustituye al timeout general existente del job.

Comprobación local: el plan contiene exactamente cuatro cadenas y cada tramo mantiene
los timestamps 1790352000–1792944000. Código de observación y análisis sin cambios
respecto de v11, cuyas 322 pruebas pasaron localmente y en Actions.

Los otros ocho fallos permanecen pendientes: HyperEVM (rango), Sei/Cronos (historia
podada), Soneium (429), Corn (proveedor), Monad/Flare/Gensyn (eth_getLogs no disponible
en los proveedores probados). No se amplía automáticamente la búsqueda ni se contrata RPC.
