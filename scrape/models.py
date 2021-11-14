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
    page_number = models.IntegerField()
    content = models.TextField()
    url = models.CharField(max_length=1024)

    def __str__(self):
        return '{}, Page {}'.format(self.publication, self.page_number)


class Sentence(SimpleModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE)
    content = models.TextField()
    percentage_maori = models.FloatField()

    def __str__(self):
        return '{}% {}'.format(self.content, self.percentage_maori)
