# Registro de programas y revisión local multiplataforma

Implementación ejecutable de `program_registry.py`, conectada a la CLI, los
Candidates existentes, AuditLog nativo de DIABLO, QA y el reporte conjunto.
No sustituye un permiso del programa ni implementa cuentas/API de plataformas.

## Qué hace

Conserva un espacio de nombres `plataforma:programa` para Immunefi, HackenProof,
Sherlock, Cantina, HackerOne, Bugcrowd, Intigriti y YesWeHack. Las ocho etiquetas
no son ocho conectores. El operador suministra un snapshot privado del alcance,
el texto de las reglas, su hash, activos exactos y una revisión con caducidad.

La revisión queda ligada por hash a TODOS los campos de la política. Cambiar
activos, reglas, documentos, participación o fechas requiere nueva revisión.
Se distinguen bounties, concursos y divulgación; los concursos pueden tener una
ventana cerrada. No se asume que la severidad, elegibilidad o recompensa de una
plataforma se transfiera a otra.

El motor evalúa alcance por repositorio+commit, chainId+dirección EVM u origen
HTTPS exacto. No expande wildcards, no sigue redirects, no incorpora subdominios
ni infiere permisos a partir de una URL. Una exclusión explícita vence siempre.
No evalúa proxy implementations ni alcanza direcciones adicionales implícitas.

`ELIGIBLE_LOCAL_REVIEW` significa únicamente que las declaraciones y archivos
suministrados satisfacen esta política local. Se conserva
`authorization_authenticated=false`. Un nombre de revisor y un hash no prueban
identidad, autorización, vigencia externa, acceso a programas privados ni que la
transcripción del alcance sea correcta.

Las acciones disponibles son `offline_source_review`, `offline_evidence_review`
y `offline_policy_review`. **No se ejecuta ninguna de ellas contra un objetivo:**
se evalúa la admisión del expediente para una revisión humana/local posterior.
Escaneo activo, ejecución de PoCs, evasión y envíos quedan fuera de esta interfaz.
La caducidad máxima de 7 días es un límite LOCAL de ingeniería, no una regla que
se atribuya a las plataformas. Las políticas pueden cambiar antes: hay que
verificarlas externamente de nuevo antes de actuar.

## Comandos

```bash
python3 -m superhunter program-platforms
python3 -m superhunter review-programs --registry /privado/registry.json \
  --requests /privado/requests.json --documents /privado/documentos \
  --out /privado/caso-nuevo
python3 -m superhunter verify-programs --bundle /privado/caso-nuevo
```

0: todos los casos son aptos para revisión LOCAL. 1: existe al menos un bloqueo.
2: entrada, artefactos o ejecución inválidos. El código 0 NO habilita pruebas,
no demuestra vulnerabilidad y no hace un envío.

El verificador reconstituye la decisión histórica y su bitácora. Además vuelve
a evaluar la vigencia con el reloj actual: una aprobación antigua no se reutiliza
como si siguiera vigente. Los dos conteos se conservan por separado.
Los paquetes contienen documentos privados, no deben subirse al repo público.

## Enlace con Candidate

`review_candidate()` valida el contrato Candidate existente y requiere programa,
scope_id, repositorio/commit y TODAS las direcciones afectadas en la cadena
explicita. Devuelve admisión o bloqueo para revisión; no ejecuta poc_path, no
inventa una Reconstruction, no modifica severidad y nunca emite Finding.
No se instala como sustituto del verificador de explotabilidad que sigue pendiente.

## Validación externa de reglas de diseño (consultadas 2026-11-04)

- HackerOne, Code of Conduct: https://www.hackerone.com/policies/code-of-conduct
- Bugcrowd, brief: https://docs.bugcrowd.com/researchers/participating-in-program/reviewing-bounty-briefs/
- Intigriti, code of conduct: https://kb.intigriti.com/en/articles/5247238-community-code-of-conduct
- Immunefi, reglas: https://immunefi.com/rules/
- HackenProof: https://docs.hackenproof.com/welcome/code-of-conduct

Estas referencias motivan el control por programa y la revisión humana. No se
usan como autorización para ningún objetivo. No se copió texto propietario ni
se conectó una cuenta. Ningún programa real está inscrito en los ejemplos.

## Próximos módulos aprobados como plan, no como implementación

La ampliación de diez líneas de trabajo queda registrada: gestión de programas;
análisis semántico; hipótesis comprobables; pruebas de propiedades con estado;
razonamiento formal acotado; conciliación económica; repetición independiente;
refutación/falsos positivos; memoria explícita revisada; evaluación ciega y costos.
Cada una reutilizará componentes cuando existan, sin asumir que registro de
requisitos equivale a módulo terminado. No hay planificador de explotación ni
promesa de detección total, falsos positivos cero o superioridad ya demostrada.

La entrega actual implementa solo la gestión local de programas descrita arriba,
y consolida los incrementos de contabilidad, enlaces Python y Z3 previos.
Los 27 requisitos, 50 capacidades y 25 iniciativas se conservan.
