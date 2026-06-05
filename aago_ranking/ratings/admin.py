from django.contrib import admin

from .models import PlayerRating, TrueSkillPlayerRating


@admin.register(PlayerRating)
class PlayerRatingAdmin(admin.ModelAdmin):
    list_display = ('event', 'player', 'mu', 'sigma')
    change_list_template = "admin/ratings/playerrating_change_list.html"


@admin.register(TrueSkillPlayerRating)
class TrueSkillPlayerRatingAdmin(admin.ModelAdmin):
    list_display = ('event', 'player', 'mu', 'sigma')
    change_list_template = "admin/ratings/trueskill_change_list.html"
