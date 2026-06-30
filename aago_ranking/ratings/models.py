from __future__ import unicode_literals

from django.db import models
from django.utils import timezone


class PlayerRating(models.Model):
    player = models.ForeignKey('games.Player', db_index=True,on_delete=models.CASCADE,)
    event = models.ForeignKey('events.Event', db_index=True,on_delete=models.CASCADE,)
    mu = models.FloatField()
    sigma = models.FloatField()

    class Meta:
        unique_together = ('player', 'event')

    def __str__(self):
        return "Rating for {s.player} at {s.event}: {s.mu}({s.sigma})".format(s=self)


class TrueSkillPlayerRating(models.Model):
    """Ratings calculados con TrueSkill Through Time.

    Se guardan en una tabla separada de ``PlayerRating`` para poder comparar
    el ranking actual (AGA/RAAGo) con el nuevo sin pisar los datos existentes.
    """
    player = models.ForeignKey('games.Player', db_index=True, on_delete=models.CASCADE)
    event = models.ForeignKey('events.Event', db_index=True, on_delete=models.CASCADE)
    mu = models.FloatField()
    sigma = models.FloatField()

    class Meta:
        unique_together = ('player', 'event')

    def __str__(self):
        return "TTT rating for {s.player} at {s.event}: {s.mu}({s.sigma})".format(s=self)


class RatingUpdateJob(models.Model):
    """Seguimiento de un recalculo de ratings corriendo en background.

    Los recalculos (AGA/raago y TrueSkill) tardan mas que el timeout del
    request HTTP, asi que se lanzan en un thread y se reporta el progreso a
    traves de esta tabla. La pagina del admin hace polling del estado.
    """
    JOB_AGA = 'aga'
    JOB_TTT = 'ttt'
    JOB_CHOICES = [
        (JOB_AGA, 'AGA ratings (raago C++)'),
        (JOB_TTT, 'TrueSkill Through Time'),
    ]

    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Corriendo'),
        (STATUS_SUCCESS, 'Terminado OK'),
        (STATUS_ERROR, 'Error'),
    ]

    # Un job "corriendo" mas viejo que esto se considera muerto (p.ej. el
    # contenedor se reinicio en medio del calculo) y deja lanzar otro.
    STALE_AFTER = timezone.timedelta(minutes=30)

    job_type = models.CharField(max_length=10, choices=JOB_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=STATUS_RUNNING)
    message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return "{s.job_type} job #{s.pk}: {s.status}".format(s=self)

    @property
    def is_stale(self):
        return (self.status == self.STATUS_RUNNING and
                timezone.now() - self.created_at > self.STALE_AFTER)
