from django.db import models

# Create your models here.
from root.models import SimpleModel


class Newspaper(SimpleModel):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Publication(SimpleModel):
    newspaper = models.ForeignKey(Newspaper, on_delete=models.CASCADE)
    published_date = models.DateField()
    volume = models.IntegerField(null=True, blank=True)
    number = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return '{}, Volumn {}, Number {}, Published {}'.format(self.newspaper.name, self.volume, self.number, self.published_date.strftime('%Y-%m-%d'))


class Page(SimpleModel):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)
    page_number = models.CharField(max_length=255)
    raw_text = models.TextField()
    url = models.CharField(max_length=1024)

    adapted_text = models.TextField()
    percentage_maori = models.FloatField(null=True, blank=True)
    maori_word_count = models.IntegerField(null=True, blank=True)
    ambiguous_word_count = models.IntegerField(null=True, blank=True)
    other_word_count = models.IntegerField(null=True, blank=True)
    total_word_count = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return '{}, Page {}'.format(self.publication, self.page_number)