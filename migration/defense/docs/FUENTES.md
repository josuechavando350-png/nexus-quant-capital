# Fuentes técnicas y límites de las afirmaciones

Consulta: 6 de noviembre de 2026. El catálogo original es el PDF adjunto; su SHA-256 aparece en `catalog_100.json`. Las correcciones siguientes delimitan capacidades, no certifican esta entrega.

- seL4, supuestos de verificación: https://sel4.systems/Verification/assumptions.html . Las garantías se apoyan en modelos y supuestos, incluidos hardware, arranque y tratamiento de DMA. No certifican automáticamente una aplicación completa ni eliminan todos los canales laterales.
- Linux, programas LSM BPF: https://docs.kernel.org/bpf/prog_lsm.html . eBPF/LSM requiere soporte real del kernel y hooks concretos. Esta entrega no afirma haberlos cargado ni medido su latencia.
- Universidad de Cambridge, CHERI: https://www.cl.cam.ac.uk/research/security/ctsrd/cheri/cheri-faq.html . Las capacidades incluyen límites y permisos protegidos por la arquitectura. Un wrapper Python no implementa CHERI.
- NIST FIPS 203: https://csrc.nist.gov/pubs/fips/203/final . ML-KEM es un mecanismo de encapsulación de claves; no equivale por sí solo a un protocolo completo de transporte.
- NIST FIPS 204: https://csrc.nist.gov/pubs/fips/204/final . ML-DSA corresponde a firmas digitales. Se deberá verificar también la errata y la implementación elegida antes de integrarlo.
- OWASP CSP: https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html . Los nonces deben generarse por respuesta y asociarse solo al contenido autorizado. No se deben añadir automáticamente a scripts inyectados.
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html . El paquete usa transacciones explícitas con `isolation_level=None` y `BEGIN IMMEDIATE`; las pruebas verifican consumo único y rollback con fallos reales de SQLite.

No se aceptan como requisitos verificables frases del documento como «ausencia absoluta de bugs», «inmunidad», «cuarentena perfecta», «atribución matemática exacta» o latencias sin medición. Las funciones dirigidas contra equipos ajenos se reformulan como análisis, validación o contención en infraestructura propia. No se implementan contraataques, reproducción de exploits ni flujos ofensivos autónomos.

Firma de expedientes 0.18: API Ed25519 de cryptography 50.0.2, https://cryptography.io/en/50.0.2/hazmat/primitives/asymmetric/ed25519/ ; vector público TEST 1 de RFC 8032 §7.1, https://www.rfc-editor.org/rfc/rfc8032#section-7.1 . Consultados el 6 de noviembre de 2026. Primitiva de biblioteca, sin implementación criptográfica propia; una firma del emisor no acredita custodia independiente ni verdad de sus afirmaciones.
