from django.contrib import admin

from .models import PlayerRating, RatingUpdateJob, TrueSkillPlayerRating


@admin.register(PlayerRating)
class PlayerRatingAdmin(admin.ModelAdmin):
    list_display = ('event', 'player', 'mu', 'sigma')
    change_list_template = "admin/ratings/playerrating_change_list.html"


@admin.register(TrueSkillPlayerRating)
class TrueSkillPlayerRatingAdmin(admin.ModelAdmin):
    list_display = ('event', 'player', 'mu', 'sigma')
    change_list_template = "admin/ratings/trueskill_change_list.html"


@admin.register(RatingUpdateJob)
class RatingUpdateJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'job_type', 'status', 'created_at', 'finished_at')
    list_filter = ('job_type', 'status')
    readonly_fields = ('job_type', 'status', 'message', 'created_at', 'finished_at')
