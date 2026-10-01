from django.db import models


class Book(models.Model):
    class Cover(models.TextChoices):
        HARD = "hard", "Hard"
        SOFT = "soft", "Soft"

    title = models.CharField(max_length=128)
    author = models.CharField(max_length=64)
    cover = models.CharField(max_length=12, choices=Cover.choices)
    inventory = models.PositiveIntegerField()
    daily_fee = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return f"'{self.title}' - {self.author}"
