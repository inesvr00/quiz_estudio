# Quiz Estudio

Aplicacion Flask para estudiar preguntas desde `preguntas.csv`.

El CSV sigue siendo la fuente de preguntas. La persistencia de uso
(`respuestas`, `aciertos`, `fallos`, preguntas vistas y progreso por tema) se
guarda en PostgreSQL cuando configuras `DATABASE_URL`. Para desarrollo local,
si `DATABASE_URL` no existe, la aplicacion usa `stats.db` como fallback.

## Instalacion

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## Base de datos

### Supabase gratis

1. Crea una cuenta en <https://supabase.com/>.
2. Crea un proyecto nuevo en el plan Free.
3. En el proyecto, abre `Project Settings` > `Database`.
4. Copia la cadena de conexion de PostgreSQL. Para un servidor Flask persistente
   suele ir bien `Session pooler`; si tu hosting abre conexiones temporales,
   usa `Transaction pooler`. Evita la conexion directa si el hosting no soporta
   IPv6. Sustituye `[YOUR-PASSWORD]` por la contrasena real de la base de datos.
5. Configura la variable de entorno `DATABASE_URL` con esa cadena.

Ejemplo en PowerShell:

```powershell
$env:DATABASE_URL="postgresql://postgres.xxxxx:password@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
```

La aplicacion anade `sslmode=require` si no viene ya en la URL.

### Crear tablas

Puedes crear las tablas de dos formas:

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py
```

O copiando el contenido de `src/quiz_estudio/db/schema.sql` en el SQL editor de
Supabase y ejecutandolo. La app tambien llama a la inicializacion al arrancar.

### Migrar estadisticas desde SQLite

Para copiar las estadisticas antiguas de `stats.db` a Supabase/PostgreSQL,
configura primero `DATABASE_URL` y asegurate de que las tablas ya existen en
PostgreSQL.

Prueba primero en modo simulacion:

```powershell
$env:DATABASE_URL="postgresql://..."
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py --dry-run
```

Si el resumen es correcto, ejecuta la migracion real:

```powershell
$env:DATABASE_URL="postgresql://..."
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py
```

El script pide confirmacion antes de insertar. Para automatizarlo:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py --yes
```

La migracion:

- lee `stats.db` en modo solo lectura,
- no modifica `preguntas.csv`,
- no borra datos de PostgreSQL,
- evita duplicados si se ejecuta mas de una vez,
- imprime filas leidas, insertadas y omitidas.

## Ejecutar

En Windows local, usa el servidor de desarrollo de Flask:

```powershell
.\.venv\Scripts\python.exe run.py
```

Tambien puedes probar la app con un servidor WSGI compatible con Windows:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5000 run:app
```

No uses `gunicorn` como prueba local en Windows: Gunicorn esta pensado para
Linux/Unix y puede fallar con `ModuleNotFoundError: No module named 'fcntl'`.

Sin `DATABASE_URL`, se usa `stats.db` local. Con `DATABASE_URL`, se usa
PostgreSQL/Supabase y el progreso queda sincronizado entre movil y ordenador.

## Despliegue en Render + Supabase

1. Crea el proyecto en Supabase y copia la URL PostgreSQL de `Session pooler` o
   `Transaction pooler`.
2. En Render, crea un `Web Service` desde el repositorio.
3. Configura el entorno como Python 3.11 o superior.
4. Usa este comando de build:

```bash
pip install -r requirements.txt
```

5. Usa este comando de arranque en Render/Linux:

```bash
gunicorn run:app
```

6. En `Environment`, anade estas variables:

```text
DATABASE_URL=postgresql://...
SECRET_KEY=una-clave-larga-y-secreta
```

7. Crea las tablas ejecutando `src/quiz_estudio/db/schema.sql` en el SQL editor
   de Supabase, o usando una shell de Render:

```bash
python scripts/init_db.py
```

No subas `.env`, `.env.*` ni `stats.db` a Git. Ya estan incluidos en
`.gitignore`; en produccion Render debe recibir los secretos desde sus variables
de entorno.

## Rutas principales

- `/`
- `/quiz`
- `/simulacro`
- `/simulacro/quiz`
- `/otra-mas`
- `/reiniciar`
- `/simulacro/reiniciar`
- `/estadisticas`
- `/preguntas-falladas`
- `/preguntas-no-hechas`
- `/importar-preguntas`

## Desplegar en PythonAnywhere

Nota importante: Supabase puede estar en plan gratuito, pero PythonAnywhere
normalmente necesita un plan de pago para conectar con bases de datos externas
por PostgreSQL. Las cuentas gratuitas tienen salida a Internet restringida a
HTTP/HTTPS mediante allowlist, y una conexion PostgreSQL a Supabase no suele
funcionar ahi.

1. Sube el proyecto a PythonAnywhere, por Git o por archivos.
2. Crea un virtualenv con Python 3.11 o superior.
3. Instala dependencias:

```bash
pip install -e .
```

4. En la pestana `Web`, crea una app Flask manual.
5. Configura el WSGI para importar la aplicacion:

```python
import sys

project_home = "/home/tu_usuario/quiz_estudio"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from run import app as application
```

6. En `Web` > `Environment variables`, anade:

```text
DATABASE_URL=postgresql://...
SECRET_KEY=una-clave-larga-y-secreta
```

7. Recarga la web desde la pestana `Web`.

## Usar desde el movil

Cuando la app este desplegada, abre la URL publica de PythonAnywhere desde el
movil. Como todos los intentos se guardan en Supabase mediante `DATABASE_URL`,
el progreso sera el mismo desde cualquier navegador.

## Archivos SQLite antiguos

- `stats.db` solo se mantiene como fallback local. No lo subas a produccion.
- Si vas a trabajar siempre con Supabase, puedes eliminar `stats.db`.
- No hay scripts de importacion ligados a SQLite; `scripts/import_questions.py`
  sigue siendo util porque importa preguntas al CSV.
