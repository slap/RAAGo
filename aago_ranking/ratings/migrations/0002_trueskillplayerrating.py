# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0002_game_event'),
        ('events', '0001_initial'),
        ('ratings', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TrueSkillPlayerRating',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mu', models.FloatField()),
                ('sigma', models.FloatField()),
                ('event', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, to='events.Event')),
                ('player', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, to='games.Player')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='trueskillplayerrating',
            unique_together=set([('player', 'event')]),
        ),
    ]
