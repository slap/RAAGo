from django.contrib import admin

from .models import PlayerRating, TrueSkillPlayerRating


@admin.register(PlayerRating)
class PlayerRatingAdmin(admin.ModelAdmin):
    list_display = ('event', 'player', 'mu', 'sigma')


@admin.register(TrueSkillPlayerRating)
class TrueSkillPlayerRatingAdmin(admin.ModelAdmin):
    list_display = ('event', 'player', 'mu', 'sigma')
