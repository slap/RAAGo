import datetime
import logging
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


def _build_dump_command():
    """Comando mysqldump nativo armado desde la config de la DB de Django.

    Funciona en el server (Railway), donde hay mysqldump nativo (default-mysql-client)
    y la DB viene de DATABASE_URL. Se puede pisar por completo con la variable de
    entorno DB_DUMP_COMMAND (p.ej. para correrlo via `docker exec` en local).
    """
    if settings.DB_DUMP_COMMAND:
        return settings.DB_DUMP_COMMAND

    db = settings.DATABASES['default']
    name = db['NAME']
    cmd = [
        'mysqldump', '--no-tablespaces', '--single-transaction',
        '-h', db.get('HOST') or '127.0.0.1',
        '-P', str(db.get('PORT') or 3306),
        '-u', db.get('USER') or 'root',
    ]
    password = db.get('PASSWORD')
    if password:
        cmd.append('-p{}'.format(password))
    cmd += ['--ignore-table={}.{}'.format(name, t) for t in _DUMP_IGNORED_TABLES]
    cmd.append(name)
    return cmd


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
