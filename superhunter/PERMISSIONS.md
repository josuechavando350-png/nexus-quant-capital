# Revisión defensiva de permisos — modelo sh-rbac-v1

El módulo `permissions.py` analiza una política JSON local aportada por el
operador. Implementa parte de los puntos 14 (grafo de permisos) y 24 (RBAC y
revocación). No importa políticas cloud, no lee contratos, no descubre objetivos
ni intenta conseguir accesos. No modifica la configuración que analiza.

## Semántica exacta

Cada usuario tiene roles asignados; todos se consideran activos. Cada rol puede
heredar permisos y denegaciones de otros roles. La herencia debe ser un DAG:
un ciclo es una configuración inválida y no se presenta como vulnerabilidad.
La denegación explícita prevalece sobre cualquier concesión. Un usuario marcado
como deshabilitado no obtiene permisos, incluso si tiene roles asignados.

La separación se expresa como un máximo de permisos de un conjunto que un mismo
usuario puede tener simultáneamente. Es una extensión de este modelo, **no una
implementación certificada de SSD/DSD de NIST**. Las revocaciones quitan solo
asignaciones directas declaradas por el usuario; se recalcula la herencia y se
comprueba si permanecen permisos que deberían desaparecer. También se informa
si retirar un rol de denegación aumenta permisos. No se generan secuencias de
ataque ni se afirma que esos cambios hayan ocurrido en producción.

La referencia conceptual de roles, herencia y separación de funciones es la
FAQ de NIST: https://csrc.nist.gov/Projects/role-based-access-control/faqs
Las decisiones específicas de precedencia, formato y límites son propias de
`sh-rbac-v1`. No confundirlas con equivalencia a IAM, Solidity o un producto.

## Dos implementaciones, sin declaraciones de éxito externas

La implementación principal propaga conjuntos en orden topológico. La segunda
recorre el grafo por usuario y calcula permisos mediante máscaras de bits.
Se comparan para cada usuario y para cada escenario de revocación explícito.
Si discrepan, se detiene la revisión. Comparten la especificación y validación
de entrada; su acuerdo no es una prueba formal ni excluye errores compartidos.

`assertions` permite declarar ALLOW/DENY esperado por usuario y permiso.
`separation_rules` y `revocations` agregan comprobaciones concretas. Sin ninguna
propiedad declarada, el estado es `POLICY_REVIEW_ONLY`, no PASS de seguridad.

## Uso

```bash
python3 -m superhunter audit-permissions --policy /ruta/privada/policy.json --out /tmp/sh-permisos-001
python3 -m superhunter verify-permissions --bundle /tmp/sh-permisos-001
```

La raíz JSON contiene: `schema_version` (entero 1), `model` (`sh-rbac-v1`),
`policy_id`, `permissions`, `roles`, `users`, `separation_rules`, `assertions` y
`revocations`. El paquete de validación incluye dos ejemplos mínimos completos.
Los identificadores son ASCII, de 1 a 64 caracteres. Se admiten hasta 64 roles,
128 usuarios y 128 permisos, 512 relaciones de herencia y 128 reglas de cada
clase. Todas las referencias deben existir; las listas no admiten duplicados.
Los límites de tamaño de artefacto de `safe_io` siguen siendo aplicables; un
modelo cuyo reporte exceda esos límites se rechaza, nunca se trunca a PASS.

`POLICY_ASSERTIONS_PASS` significa que se cumplieron las propiedades declaradas
EN EL MODELO. `POLICY_ASSERTIONS_FAIL` conserva evidencia de los incumplimientos.
El código de salida es 0 para un análisis sin incumplimientos declarados (incluido
REVIEW_ONLY), 1 para incumplimientos y 2 para error de entrada/IO/verificación.
Siempre `live_enforcement_verified=false` y `vulnerability_confirmed=false`.

## Evidencia y conexión

La CLI conecta al componente `permissions` del control de calidad. La bitácora
utiliza el AuditLog nativo y fijado de DIABLO. Cada comprobación queda ligada a
su hash y resultado; el verificador vuelve a calcular la política, el grafo,
los reportes y las relaciones de los eventos. Las pruebas del componente entran
en `check`, `review-platform` y los reportes globales. El comando global no
pretende haber comprobado una política de producción: ejecuta tests locales.

Se guardan `policy.json`, `analysis.json`, `graph.json`, `audit.json`,
`receipt.json`, `REVIEW.md` y `COMPLETE.json`. Son material privado. El informe
se filtra para presentación; no se alteran los originales. Los hashes no
constituyen una firma ni autentican al productor externo. Los directorios de
salida deben ser nuevos, privados y fuera del código fuente.

La validación actual y sus limitaciones están en `permissions-validation.json`.
Los recibos anteriores son históricos, no se reutilizan como prueba actual.
