# Quiz Estudio

Aplicacion Flask para estudiar preguntas tipo test.

## Estado Actual

- El banco de preguntas activo es `preguntas_nuevo_formato.csv`.
- El CSV es la fuente de verdad editable de las preguntas.
- Supabase/PostgreSQL, mediante `DATABASE_URL`, es la base oficial para estadisticas, resultados e intentos.
- Supabase tambien puede mantener una copia sincronizada del banco de preguntas para lectura futura.
- No hay backend SQLite activo.

## Variables De Entorno

Variables necesarias para ejecutar la app:

```text
DATABASE_URL=postgresql://...
SECRET_KEY=una-clave-larga-y-secreta
APP_PASSWORD=opcional-si-se-usa-en-tu-despliegue
QUESTION_REPOSITORY_BACKEND=csv
```

En Render configura al menos:

```text
APP_ENV=production
DATABASE_URL=postgresql://...
SECRET_KEY=una-clave-larga-y-secreta
```

Si falta `DATABASE_URL`, la app falla con un error claro. No crea una base local.

Para sincronizar preguntas hacia Supabase:

```text
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_DATABASE_URL=postgresql://...
```

## Instalacion Local

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Ejecuta la app:

```powershell
$env:DATABASE_URL="postgresql://..."
$env:SECRET_KEY="dev-secret"
.\.venv\Scripts\python.exe run.py
```

Tambien puedes usar Waitress en Windows:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5000 run:app
```

## Preguntas

El CSV activo es `preguntas_nuevo_formato.csv` y usa estas columnas:

```text
question_id
enunciado
respuesta_correcta
opcion_falsa_1
opcion_falsa_2
opcion_falsa_3
explicacion
tema
teoria
```

`respuesta_correcta` contiene el texto correcto. Las columnas `opcion_falsa_*`
contienen distractores. Cada pregunta debe tener un `question_id` estable tipo
`q_000001`.

Auditar el CSV:

```powershell
.\.venv\Scripts\python.exe scripts\audit_questions.py
```

Asignar IDs faltantes, si alguna fila nueva llega sin `question_id`:

```powershell
.\.venv\Scripts\python.exe scripts\ensure_question_ids.py
```

Importar preguntas desde la interfaz:

```text
/importar-preguntas
```

La importacion escribe siempre en el formato actual del CSV.

## Sincronizacion CSV -> Supabase

El workflow `.github/workflows/sync-questions-to-supabase.yml` sincroniza el CSV
con Supabase al hacer push a `main` cuando cambian las preguntas o el codigo de
sincronizacion. Tambien se puede lanzar manualmente desde GitHub Actions.

Dry-run local:

```powershell
.\.venv\Scripts\python.exe scripts\sync_questions_to_supabase.py
```

Aplicar cambios:

```powershell
.\.venv\Scripts\python.exe scripts\sync_questions_to_supabase.py --apply
```

Comprobar paridad CSV <-> Supabase:

```powershell
.\.venv\Scripts\python.exe scripts\check_question_repository_parity.py
```

Diagnosticar backends antes de cambiar Render:

```powershell
.\.venv\Scripts\python.exe scripts\check_question_backends.py
```

## Base De Datos

Las tablas de estadisticas/resultados se crean con:

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py
```

O copiando `src/quiz_estudio/db/schema.sql` en el SQL editor de Supabase.

Las tablas del banco de preguntas sincronizado se crean con:

```text
src/quiz_estudio/db/supabase_questions_schema.sql
```

Ese schema solo crea `questions` y `answer_options`; no toca tablas de intentos
o estadisticas.

## Archivos Archivados

Los datos y scripts retirados viven en `archive/`:

- `archive/old_databases/`
- `archive/old_csv/`
- `archive/old_scripts/`

Nada dentro de `archive/` es importado ni usado por la aplicacion.

## Verificacion

```powershell
.\.venv\Scripts\python.exe -m py_compile run.py
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest -q
```
