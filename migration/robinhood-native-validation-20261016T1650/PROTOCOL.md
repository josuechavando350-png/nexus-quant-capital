# Protocolo nuevo: conservar precompilados y validar controles locales

16/oct/2026. Primer incremento de los dos acotados aceptados por Chavando.
Base PR24 `6c206d67f80db206e1ffb5290e34035d9c1960dc`. Publicar este código,
reglas, orden y lock en GitHub ANTES de ejecutar. Un único piloto nuevo.

Hipótesis: el rechazo AA23 de PR24 provino de desactivar ecrecover mediante un
override de saldo. Integrar `prepare_next.preserve_native_precompiles` ya probado:
saldo/nonce de nativos Shanghai1–9 se conservan en genesis, con ausencia de sus
direcciones en stateOverrides. Rechazar código/estado no vacío/movimientos y
colisiones; no reemplazar lógica nativa. Todos los contratos/calldata/firmas de
los cinco controles previos permanecen iguales, salvo el control negativo nuevo.
Conservar intacta la captura fallida y todas las fuentes anteriores.

Mismo Geth1.17.8 binario firmado, AA/EntryPointSimulations, tracer y runtime fijados
en PR24. No nueva compilación ni dependencias. No se reinicia el instalador que
quedó bloqueado; no se evita la denegación anterior. Sólo collector oficial:
ValidationManager, parser ERC-7562, mempool y servicio comercial NO se ejecutan.

## Orden y criterios registrados

Genesis privado chainId4663/timestamp1789786800, Shanghai, sin peers/discovery,
HTTP127.0.0.1:18571 y EngineAPI127.0.0.1:18572. Puertos libres antes de arrancar.
No fork, RPC Robinhood, transacción, nueva firma, clave real, despliegue o gasto.
Los saldos/stake son fixtures. Todas las llamadas usan el mismo hash de genesis.

1. `web3_clientVersion`, `eth_chainId`, cabecera latest: comprobar versión/chain/tiempo.
2. `original_31s_unstaked`: firma original, depósito0.1ETH/stake0, ventana31s.
   Exigir retorno de simulateValidation, accountValidationData0, prefund exacto,
   stake0/contexto vacío/validez exacta y lectura/escritura del presupuesto slot1.
   La llamada nativa ecrecover debe consumir3000gas y devolver32bytes no cero.
3. `invalid_signature`: misma operación y estado que anterior; sustituir sólo los
   65bytes de firma por ceros. Exigir AA23/ECDSAInvalidSignature, ecrecover nativo
   con3000gas/retorno vacío, sin llegar al paymaster. Sin nueva firma.
4. `31s_stake_fixture`: firma original y stake1ETH/delay86400s de laboratorio.
   Mismas comprobaciones positivas, stake devuelto conforme al fixture.
5. `1s_stake_fixture`: variante histórica de ventana1s, mismo control nativo/stake.
   Retorno EVM no implica que el bundler acepte su vigencia.
6. `31s_zero_deposit`: depósito0; exigir revert con marcador AA31.
7. `31s_zero_budget`: presupuesto0; exigir revert con marcador BUDGET_POLICY.
8. Cabecera final: mismo hash/stateRoot que antes. No stateOverrides persistentes.

Plan total10RPC secuenciales:3identidad/cabecera+6trazas+1cabecera final. No aislar
un sublote para resetear límites. Máximo512RPC/900sTOTAL desde antes de inicializar
Geth, incluidos arranque/pausas. Gate350ms entre inicios sin crédito acumulable;
reserva20s antes del envío y revisión tras esperar. TimeoutHTTP20s/tracer10s,
límite2MiB por respuesta, conservar prefijo límite+1 si se excede. Sin reintentos,
redirecciones, HTTP paralelo, rotación o sesión de rescate. Endpoint literal local;
proxy externo y CA sin cambios. No métodos de envío disponibles.

ErrorHTTP/JSON/RPC/límite o resultado inesperado detiene todo y conserva prefijo,
cuerpos, inputs y logs. Reverts esperados de controles negativos son resultados
de la EVM. No relanzar/sustituir captura. Directorio de salida debe ser nuevo.
Cerrar Geth al finalizar; ignorar db/clave de nodo/JWT local en Git. Registrar UTC,
duración monotónica y proceso detenido. Una parada puede impedir cabecera final.

## Qué se puede concluir

Éxito: corregida esa causa local y observados seis controles exactos. No equivale
a admisión completa, ejecución de ruta, Nitro/DA, gas comercial ni financiación.
Stake1ETH/depósito0.1ETH no son mínimos comerciales, fondos ni compromisos reales.
La lógica del bundler sobre stake y >30s restantes sólo fue leída; no la simular
como si se hubiera ejecutado. Una ventana1s puede retornar correctamente en EVM.

14 pruebas offline nuevas ejercen integración, firma negativa, native gas/retorno,
diez fronteras RPC interrumpidas, resultado inesperado, cabecera cambiada, gate,
plazo antes/después de esperar, HTTP429/JSON/bytes y ausencia de reintentos/envíos.
Los fixtures artificiales de esas pruebas NO son evidencia Geth.

Después de captura: auditor offline de cuerpos/hash/entradas/orden/paradas, informe
separado CAPTURE.md y manifiesto. No editar este protocolo ni lock retroactivamente.
No ampliar inventarios: el segundo incremento debe evaluar admisión/financiación
con límites honestos. Si siguen bloqueadas bajo cero capital propio, proponer
congelar desarrollo activo conservando todo, sin concluir imposibilidad universal.
