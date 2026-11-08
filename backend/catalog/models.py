from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    ICON_CHOICES = [
        ('🎧', 'Electronics'), ('📷', 'Cameras'),
        ('🚲', 'Bikes'), ('🔧', 'Tools'), ('🪑', 'Furniture'),
        ('⛺', 'Camping'), ('🏸', 'Sports'), ('🎉', 'Events'), ('📦', 'General'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True, default='')
    icon = models.CharField(max_length=50, default='📦')
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Categories'

    def save(self, *args, **kwargs):
        if not self.slug or (self.pk and Category.objects.filter(pk=self.pk).values_list('name', flat=True).first() != self.name):
            base = slugify(self.name) or 'category'
            slug, n = base, 1
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f'{base}-{n}'
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Item(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True, default='')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_items', null=True, blank=True)
    rental_price = models.DecimalField(max_digits=10, decimal_places=2)
    deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, blank=True)
    stock = models.PositiveIntegerField(default=1)
    is_published = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug or (self.pk and Item.objects.filter(pk=self.pk).values_list('name', flat=True).first() != self.name):
            base = slugify(self.name) or 'item'
            slug, n = base, 1
            while Item.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f'{base}-{n}'
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def primary_image_url(self):
        img = self.images.filter(is_primary=True).first() or self.images.first()
        return img.image.url if img and img.image else None


class ItemImage(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='item_images/')
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'id']

    def __str__(self):
        return f"Image for {self.item.name} ({'Primary' if self.is_primary else 'Gallery'})"


class RentalKitItem(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='rental_kit_items')
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.name} ({self.item.name})"
