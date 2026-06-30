import datetime
import logging
import shutil
import subprocess
import threading
import traceback

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connections, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import tasks
from .models import RatingUpdateJob

logger = logging.getLogger(__name__)


def _start_job(job_type, runner):
    """Crea un RatingUpdateJob y lo corre en un thread en background.

    Devuelve (job, error_response). Si ya hay un job del mismo tipo corriendo
    (y no esta colgado), devuelve (None, JsonResponse 409).
    """
    active = (RatingUpdateJob.objects
              .filter(job_type=job_type, status=RatingUpdateJob.STATUS_RUNNING)
              .first())
    if active is not None and not active.is_stale:
        return None, JsonResponse(
            {'status': active.status, 'job_id': active.pk,
             'message': 'Ya hay un recalculo de este tipo corriendo.'},
            status=409)

    job = RatingUpdateJob.objects.create(job_type=job_type)

    def _run():
        try:
            message = runner()
            job.status = RatingUpdateJob.STATUS_SUCCESS
            job.message = message or 'Listo.'
        except Exception:  # noqa: BLE001 - queremos registrar cualquier fallo
            logger.exception("Fallo el job de ratings %s (#%s)", job_type, job.pk)
            job.status = RatingUpdateJob.STATUS_ERROR
            job.message = traceback.format_exc()
        finally:
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'message', 'finished_at'])
            # El thread usa su propia conexion a la DB; hay que cerrarla.
            connections.close_all()

    # Arrancar el thread recien cuando la transaccion del request (ATOMIC_REQUESTS)
    # haya commiteado, asi la fila del job ya es visible para el thread.
    transaction.on_commit(
        lambda: threading.Thread(target=_run, daemon=True).start())

    return job, None


@staff_member_required
@require_http_methods(["POST"])
def run_ratings_update(_request):
    """Lanza en background el recalculo del ranking AGA (raago/C++)."""
    def runner():
        result = tasks.run_ratings_update_cpp()
        return "Ranking AGA actualizado: {} eventos recalculados.".format(len(result))

    job, error = _start_job(RatingUpdateJob.JOB_AGA, runner)
    if error is not None:
        return error
    return JsonResponse({'status': job.status, 'job_id': job.pk}, status=202)


@staff_member_required
@require_http_methods(["POST"])
def run_ttt_ratings_update(_request):
    """Lanza en background el recalculo TrueSkill Through Time."""
    def runner():
        result = tasks.run_ratings_update_ttt()
        return result.get('message', 'Ranking TrueSkill actualizado.')

    job, error = _start_job(RatingUpdateJob.JOB_TTT, runner)
    if error is not None:
        return error
    return JsonResponse({'status': job.status, 'job_id': job.pk}, status=202)


@staff_member_required
@require_http_methods(["GET"])
def rating_job_status(_request, job_id):
    """Estado de un job de recalculo (para el polling del admin)."""
    job = get_object_or_404(RatingUpdateJob, pk=job_id)
    return JsonResponse({
        'status': job.status,
        'message': job.message,
        'finished': job.finished_at is not None,
    })


# Tablas de login social: no se usan y tienen columnas `json` / FKs que rompen
# en MySQL/MariaDB viejos (como el de la web de la AAGo). Se excluyen del dump.
_DUMP_IGNORED_TABLES = (
    'socialaccount_socialaccount',
    'socialaccount_socialapp',
    'socialaccount_socialapp_sites',
    'socialaccount_socialtoken',
)


def _mysqldump_args(name, host, port, user, password):
    args = [
        'mysqldump', '--no-tablespaces', '--single-transaction',
        '-h', host, '-P', str(port), '-u', user,
    ]
    if password:
        args.append('-p{}'.format(password))
    args += ['--ignore-table={}.{}'.format(name, t) for t in _DUMP_IGNORED_TABLES]
    args.append(name)
    return args


def _build_dump_command():
    """Arma el comando de dump y funciona igual en local y en el server.

    Se construye desde la config de la DB de Django (DATABASES['default']), asi
    que toma sola las credenciales correctas en cada entorno:

    - Si hay ``mysqldump`` nativo en el PATH (el server/Railway lo trae via
      default-mysql-client) -> se corre directo contra la DB.
    - Si no lo hay (p.ej. Windows en local) -> se corre ``mysqldump`` DENTRO del
      contenedor Docker de MySQL, donde la DB escucha en 127.0.0.1:3306.

    Se puede pisar todo con la variable de entorno DB_DUMP_COMMAND.
    """
    if settings.DB_DUMP_COMMAND:
        return settings.DB_DUMP_COMMAND

    db = settings.DATABASES['default']
    name = db['NAME']
    user = db.get('USER') or 'root'
    password = db.get('PASSWORD')

    if shutil.which('mysqldump'):
        host = db.get('HOST') or '127.0.0.1'
        port = db.get('PORT') or 3306
        return _mysqldump_args(name, host, port, user, password)

    # Sin mysqldump nativo: correrlo dentro del contenedor. Adentro la DB esta
    # en 127.0.0.1:3306 (su puerto interno), no el puerto mapeado al host.
    container = settings.DB_DUMP_DOCKER_CONTAINER
    return ['docker', 'exec', container] + _mysqldump_args(
        name, '127.0.0.1', 3306, user, password)


@staff_member_required
@require_http_methods(["GET"])
def download_db_dump(_request):
    """Genera un dump mysqldump de la base y lo ofrece como descarga.

    Por defecto corre mysqldump nativo contra la DB de DATABASE_URL; se puede
    pisar el comando completo con la variable de entorno DB_DUMP_COMMAND.
    """
    dump_command = _build_dump_command()
    try:
        result = subprocess.run(
            dump_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as exc:
        return HttpResponse(
            "No se pudo ejecutar el comando de dump ({}): {}".format(
                dump_command, exc),
            status=500, content_type="text/plain; charset=utf-8")
    except subprocess.CalledProcessError as exc:
        return HttpResponse(
            "mysqldump fallo (codigo {}):\n{}".format(
                exc.returncode, exc.stderr.decode("utf-8", "replace")),
            status=500, content_type="text/plain; charset=utf-8")

    filename = "RAAGo-{}.sql".format(datetime.date.today().isoformat())
    response = HttpResponse(result.stdout, content_type="application/sql")
    response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
    return response
