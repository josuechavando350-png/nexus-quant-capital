# Plan de ejecución defensiva y continuidad

Ámbito vigente: solo `NQC-defensive`, `migration/defense/` y `migration/DEFENSE-INTEGRATION.md`. SuperHunter permanece independiente. Sin publicación en main, despliegues, workflows activos ni cambios a fuentes recuperadas. Los catálogos C001–C100 y D001–D100 definen la amplitud; cada entrega debe aportar un recorrido ejecutable y evidencia.

| Requisito | Evidencia disponible | Trabajo que falta |
|---|---|---|
| Integración real | Integridad local, JSONL y formatos OpenSSH/journald llegan a la misma vista de eventos/casos | Más fuentes, autenticidad de origen y contrato distribuido |
| Precisión evaluada | Nueve escenarios sintéticos con errores visibles | Corpus independiente, etiquetas revisadas, cobertura y calibración por entorno |
| Respuesta controlada | Bloqueo/restauración del lector local; autenticación solo informa | Conectores autorizados, límites de impacto y verificación de reversión |
| Resistencia a fallos | Transacciones, reinicio, concurrencia, rotación y terminación antes del commit | Cortes eléctricos, fallos distribuidos y capacidad sostenida |
| Protección de la plataforma | Rutas acotadas, permisos locales, configuración fijada | Identidad administrativa, separación del SO, rotación de claves de auditoría y anclaje externo |
| Operación utilizable | CLI, revisión local e informes verificables offline con referencias | Resolución tras respuesta/recuperación y consola |
| Eficiencia medida | Medición local de CPU/tiempo/memoria/tamaño | Matriz de cargas, latencias de cola, degradación y costos reales |
| Validación independiente | Código, pruebas y límites reproducibles en Git | Revisión por terceros y reproducción fuera de este entorno |

Orden siguiente:

1. Revisar falsos positivos y puntos ciegos de la regla de autenticación con un conjunto separado de evaluación. No optimizar una cifra sobre los mismos nueve ejemplos.
2. Adaptadores de formato OpenSSH/journald incorporados en 0.12; falta captura autorizada en un entorno real y autenticidad de origen. Mantener separación entre observar un registro y demostrar su autenticidad.
3. Evidencia preservada (0.13) y revisión con credenciales locales (0.14) incorporadas. Renovación/revocación locales incorporadas en 0.15; caducidad optativa y control del reloj incorporados en 0.16; expedientes en 0.17 y declaraciones de emisor verificables con clave pública en 0.18; continuar con anclaje independiente, recuperación temporal y rotación de la clave de auditoría; la posesión de credenciales no equivale a identidad humana ni custodia externa.
4. Preparar una respuesta específica reversible en laboratorio, con permiso explícito, límites y prueba del servicio después de actuar.
5. Ampliar mediciones e integración por plataforma. La activación productiva tendrá alcance propio y no se presume por publicar código.

No contar documentos o pruebas como componentes completos. No calcular avance global dividiendo filas parciales entre 100. Registrar por componente alcance implementado, aceptación ejecutada y límites pendientes.

Cada cierre debe incluir las métricas de PROGRESO.md: cierres/200 y porcentaje no cerrado, más cobertura parcial de componentes y criterios del bloque trabajado. El validador exige aceptación documentada y hashes de evidencia para contar cierres.
