# Resultado — ejecución económica NQC NO DEMOSTRADA

21 de octubre de 2026. Investigación únicamente; no se firmó, transmitió o desplegó en mainnet,
no se enviaron bundles, no se usaron wallets, no se compraron servicios y no se modificó main.

1. **Estado histórico completo:** no. Se recuperaron metadatos indexados del padre/objetivo y ABI Morpho,
   pero faltan calldata, receipt, cabeceras completas y estado histórico de las dependencias.
2. **Replay original:** no ejecutado. La puerta de inputs falla con código 2, antes de una instrucción EVM.
3. **NQC con capital propietario cero:** no probado. A/B permanecen bloqueadas por el original.
4. **Beneficio neto NQC:** indeterminado (`null`), no 84.308093 ni 23.882951 USDC. No hay ganancia NQC demostrada.
5. **Titan:** mecanismo de patrocinio documentado; aceptación, selección e inclusión de NQC no demostradas.
6. **Captura de oportunidad:** no acreditada ex ante. La liquidación del tercero ya es histórica.
7. **Código y evidencia:** publicados en esta carpeta nueva; ver README, comandos y manifiesto de hashes.
8. **Bloqueo decisivo:** endpoint archivístico autorizado y alcanzable. `NQC_RPC_URL` no está configurado;
   las dos alternativas públicas dieron HTTP 403 y Blockscout REST exigió reconfiguración PRO.

## Resultados concretos

- Checkout propio desde el HEAD remoto autorizado. Evidencia anterior conservada byte a byte.
- Paquete adjunto inspeccionado y sondeo ejecutable conservado sin modificaciones.
- Verificados los hashes de los bloques y metadatos mediante Blockscout; ABI descargado.
- Foundry 1.8.5 descargado con digest oficial verificado. Binarios locales previos y Solidity 0.8.26
  cotejados con sus publicaciones oficiales. No se presentan como una reproducción EVM.
- Adquisidor de solo lectura con mensajes de error preservados y secretos redactados; no reintenta 4xx.
- Puerta de inputs que no confunde metadatos/ABI con estado completo, ni inputs presentes con replay.
- Contabilidad por activo reproducida con enteros/fracciones; costes desconocidos permanecen `null`.
- 45 pruebas Python aprobadas: 22 del analizador anterior, 8 simuladas del sondeo adjunto,
  9 de aislamiento y 6 de seguridad/contabilidad. Ninguna es prueba de rentabilidad de NQC.
- Verificador completo de aislamiento aprobado: 531 archivos de origen, 106 workflows desactivados,
  cero workflows activos. No se consultó el repositorio original prohibido ni se recertificó su evidencia.
- No se ejecutó Rust (sin cambios en Rust), Solidity, fork original, variante NQC ni CI remoto.

La valoración histórica condicional de aproximadamente 20.670421 USDC equivalentes del tercero
depende de consolidar direcciones y valorar ETH/WETH al ratio del swap observado. No es cotización
de salida ejecutable ni P&L íntegro auditado, y no es beneficio de NQC.

Para continuar: configurar una clave Alchemy vigente como secreto `NQC_RPC_URL` en el entorno de ejecución,
sin pegarla en reportes/commits, y ejecutar el colector en una red que permita el endpoint.
La clave por sí sola no garantiza que la restricción de transporte desaparezca. También sirve aportar
las respuestas crudas exportadas desde ese entorno autorizado. No se solicita contratar Blockscout.

Confianza: alta en el bloqueo observado, los hashes de los archivos publicados y la aritmética del
alcance declarado. Rentabilidad/captura NQC: no evaluable con estos datos; no se inventa un porcentaje.
