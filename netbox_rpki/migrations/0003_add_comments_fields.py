# Generated by Django 5.0.9 on 2024-11-06 00:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0002__add_tenancy'),
    ]

    operations = [
        migrations.AddField(
            model_name='certificate',
            name='comments',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='organization',
            name='comments',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='roa',
            name='comments',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='roaprefix',
            name='comments',
            field=models.TextField(blank=True),
        ),
    ]