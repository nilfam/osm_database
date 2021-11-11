# Generated by Django 2.0.4 on 2021-11-01 04:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Newspaper',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Page',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('page_number', models.IntegerField()),
                ('content', models.TextField()),
                ('url', models.CharField(max_length=1024)),
            ],
        ),
        migrations.CreateModel(
            name='Publication',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('published_date', models.DateField()),
                ('volume', models.IntegerField(blank=True, null=True)),
                ('number', models.IntegerField(blank=True, null=True)),
                ('newspaper', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scrape.Newspaper')),
            ],
        ),
        migrations.AddField(
            model_name='page',
            name='publication',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scrape.Publication'),
        ),
    ]