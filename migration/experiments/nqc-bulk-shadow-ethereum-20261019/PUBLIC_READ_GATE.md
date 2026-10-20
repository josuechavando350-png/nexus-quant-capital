# Condiciones operativas para la primera captura MASIVA de datos reales

- La función de red está INACTIVA por defecto. No se ha llamado ninguna API de Morpho en esta entrega.
- Los dos destinos permitidos son exclusivamente `https://api.morpho.org/graphql` y `https://api.morpho.org/v1/blue/markets` por GET/POST de lectura, respectivamente.
- **No ejecutar en el runtime DNS bloqueado de NQC067. No reintentar el Desktop Commander, con cuota mensual agotada, ni utilizar un proveedor alterno para evadir un bloqueo.** Solo autorizar en un entorno nuevo, legítimamente conectado y habilitado por el propietario, con reglas de cuota explícitas.
- En una ejecución autorizada, iniciar con directorio de evidencia VACÍO y único, confirmar que no existe `MANUAL_REVIEW_REQUIRED`. El primer error 403/429/5xx/DNS crea un bloqueo manual; no repetir una petición de salida ambigua ni reanudar automáticamente.
- Descubrimiento global: `marketPositions` con `chainIds:[1]`, `hfLte:1.02`, `marketListed:true`, `first:1000`, páginas `skip: 0,1000,...` hasta un máximo de diez respuestas. Si faltan páginas, hay repetidos o cambian los totales, cobertura INCOMPLETA. El filtro de salud es del indexador, no del oráculo onchain.
- Directorio REST: `/v1/blue/markets?chain_id=1&limit=1000` con el cursor de la respuesta anterior, exactamente, hasta diez páginas. Si el cursor final no es `null`, censo INCOMPLETO. Configuración de mercado no es elegibilidad de liquidación.
- Guardar cuerpos crudos, SHA256 y hora local observada de la ejecución; estos hashes NO autentican EVM. No almacenar credenciales, wallets, gas, claves ni configuraciones de firma.
- **Puerta de negocio**: para cada finalista demostrar elegibilidad EVM/oráculo, cantidad de repago, salida de colateral al tamaño exacto, gas, inclusión, financiamiento, competencia y no recurso personal. Sin todas estas pruebas, neto y admisión siguen `null`/`false`. Queda prohibido presentar la diferencia USD de la interfaz como ingreso realizado.

NQC055 sigue siendo la autoridad de aritmética económica por unidades exactas; este módulo solo descubre candidatos y conserva la evidencia de filtro. No hay ninguna autorización para reactivar GitHub Actions, enviar bundles ni implementar Canary.
