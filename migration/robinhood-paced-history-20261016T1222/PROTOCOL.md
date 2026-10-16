# Protocolo nuevo: historia contigua + cola + cobertura actual

Preparado el 16/oct/2026 sobre PR18 `9063049967530a682d28d94af5ff17cf46c7bd66`.
Este archivo y las fuentes se publican **antes** de consultar. Resultados reales
posteriores irán en README/evidence, sin modificar este protocolo.

## Hipótesis y selección

Ampliar historia puede descubrir prestatarios aún ausentes y aumentar cobertura
de borrowShares. No se presupone que sean liquidables ni rentables. Ventana
fijada **88,246,281–88,646,280**, exactamente 400,000 bloques inmediatamente
anteriores al registro PR18. Selección independiente de salud y liquidaciones
conocidas. Conservar cuentas de deuda cero y todos los eventos previos.

Fuente: `migration/robinhood-paced-acquisition-20261016T1024/evidence/pilot/registry.json`.
Raíz `8740288f2899e8fc2056d56291ad5369f8c37d46a1e8139a5b41f3501601aaf0`;
SHA archivo `0346642a39cc0227bee8aa6e16f6a592d45fdb5e8ffbb29bb01a4c82aa5774d6`.
Intervalo previo 88,646,281–90,037,169, 61 Borrow y 31 cuentas. Nunca usar una
traza sintética como fuente. Se guardan bytes de entrada sin cambios.

## Orden fijo y conservación

1. Validar fuente/hash/ventana offline; guardar registro de base antes de RPC.
   Verificar chainId, checkpoint previo y límite entre historia/fuente.
2. Guardar registro histórico vacío y actualizarlo en 40 segmentos de hasta
   10,000 bloques, sin saltos. Confirmar cabeceras de eventos y fin de segmento;
   verificar otra vez el límite final. Conservar `older-registry.json` parcial.
3. Unir con el helper puro probado. Revalidar checkpoint de fuente. Conservar
   `merged-before-catchup.json` y promover `registry.json` al prefijo unido solo
   después de esas comprobaciones. Los enlaces SHA entre segmentos se reconstruyen;
   logs, eventos y cabeceras previos se conservan exactamente y la fuente original
   queda intacta. No se declara una cohorte completa todavía.
4. Pedir cabecera vigente y anchor a 64 bloques. Continuar cola desde
   **90,037,170**, revalidando checkpoint. Máximo 40 segmentos de cola; si no
   cabe, parar, nunca saltar huecos. Autenticar contratos/mercado en el anchor.
5. Congelar solo tras target completo y autenticado. Realizar **tres** rondas
   secuenciales: latest, lectura única lens fijada por hash/requireCanonical,
   cabecera canónica y derivación/reconciliación contra totalBorrowShares.
   Retener cabeceras repetidas y rondas lentas, rechazar regresiones/reorgs.
   No comparar tres transportes ni cambiar el orden según resultados.

## Límites globales, transporte y latencia

**Una sola sesión persistente, sin rotación**, para todas las fases. Un solo
contador de máximo **512 métodos RPC**, un solo plazo de **900 s** desde inicio
(esperas incluidas), un único gate de **350 ms mínimos entre inicios locales**.
No acumular crédito ni reiniciar límites al cambiar de fase. Prefijos de fase
en las etiquetas permiten auditar el orden y las fronteras.

Endpoint único heredado `https://docs-demo.robinhood-mainnet.quiknode.pro/`.
TLS verificado, proxy/no_proxy/CA intactos, mismas dependencias exactas PR15.
Timeout máximo 20 s por llamada limitado al plazo restante, 2 MiB por cuerpo,
32 MiB acumulados. No reintentos, redirecciones, HTTP paralelo, nuevo proveedor,
sesión de rescate ni cambios de red para eludir denegaciones. Cualquier error
detiene la captura completa y conserva cuerpo, ledger, admisiones y journal.
Separación local no garantiza cuota compartida, llegada al servidor o SLA.

Métrica primaria de cada lectura: antes de esperar admisión de cabecera hasta
estado verificado. Reportar también desde despacho, entradas y espera inicial.
Las tres rondas usan la sesión ya empleada en indexar: **no son arranques fríos**.
Retener metadatos de socket sin inferir conexión backend. No excluir esperas
para forzar el objetivo supuesto de 1 s ni afirmar cadencia sostenida con tres
rondas. No incluye ruta, envío/inclusión, gas o financiación.

## Pruebas y auditoría

`test_history.py` prueba el nuevo flujo con reloj inyectado: 43 fronteras RPC
sintéticas, fallo inmediatamente después de unión y antes de catch-up, errores
HTTP/JSON/RPC, límites globales en cada fase, reorgs y corrupción de archivos.
`audit_history.py` reproduce el control de flujo sin red y exige coincidencia
exacta de presencia/bytes de los cuatro archivos de estado, incluidos prefijos.
El auditor también verifica gate/admisiones y preservación de fuentes.

Los helpers anteriores se reutilizan; no se ejecutan mains de ventanas antiguas.
Fuentes transitivas fijadas en `registration-sources.json`; resultados y hashes
offline en `evidence/verification`. Publicar registro antes de la captura única;
no sustituir una parada con otro intento. Prefijos no completados no equivalen
a cohorte congelada; ausencia de observación no equivale a cero candidatos.

Sin transacciones, firmas, trading, claves, gastos, suscripciones o despliegues.
No tocar workflows u otros repositorios. Deuda y simulación no son ingresos.
Rentabilidad, costes AA/Nitro/DA, admisión y patrocinio financiable no demostrados.
