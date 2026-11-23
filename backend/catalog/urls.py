from django.urls import path
from .views import CategoryListCreateView, CategoryDetailView, CategorySoftDeleteView

urlpatterns = [
    path('',              CategoryListCreateView.as_view(),  name='category-list'),
    path('<int:pk>/',     CategoryDetailView.as_view(),      name='category-detail'),
    path('<int:pk>/delete/', CategorySoftDeleteView.as_view(), name='category-soft-delete'),
]