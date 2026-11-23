from django.contrib import admin
from .models import Category, Item, ItemImage, RentalKitItem, WishlistItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'icon', 'is_active', 'is_deleted', 'created_at']
    list_filter = ['is_active', 'is_deleted', 'icon']
    search_fields = ['name', 'slug']
    readonly_fields = ['slug', 'created_at', 'updated_at']


class ItemImageInline(admin.TabularInline):
    model = ItemImage
    extra = 1


class RentalKitItemInline(admin.TabularInline):
    model = RentalKitItem
    extra = 1


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'rental_price', 'stock', 'deposit', 'is_published', 'is_deleted', 'created_at']
    list_filter = ['is_published', 'is_deleted', 'category']
    search_fields = ['name', 'slug', 'description']
    readonly_fields = ['slug', 'created_at', 'updated_at']
    inlines = [ItemImageInline, RentalKitItemInline]


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'item', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__email', 'item__name']
    readonly_fields = ['created_at']

