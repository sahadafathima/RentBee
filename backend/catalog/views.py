import json
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.permissions import IsAdminUser
from .image_utils import process_item_image
from .models import Category, Item, ItemImage
from .serializers import CategorySerializer, ItemSerializer


# ==========================================
# CATEGORY VIEWS (Admin)
# ==========================================

class CategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        # Exclude reserved "All Categories" sentinel — it must never appear as a real DB category
        qs = Category.objects.filter(is_deleted=False).exclude(name__iexact='all categories').exclude(icon='▦')
        if search := self.request.query_params.get('search'):
            qs = qs.filter(Q(name__icontains=search) | Q(slug__icontains=search))
        if (status_p := self.request.query_params.get('status')) in {'active', 'inactive'}:
            qs = qs.filter(is_active=(status_p == 'active'))
        qs = qs.annotate(items_count=Count('items', filter=Q(items__is_deleted=False)))
        sort = self.request.query_params.get('sort', '-created_at')
        allowed_sorts = {'-created_at', 'created_at', 'name', '-name', 'items_count', '-items_count'}
        return qs.order_by(sort if sort in allowed_sorts else '-created_at')

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        results = self.get_serializer(qs, many=True).data
        used_icons = list(Category.objects.filter(is_active=True, is_deleted=False).values_list('icon', flat=True).distinct())
        total_items = Item.objects.filter(is_deleted=False).count()
        return Response({
            'count': len(results), 'results': results,
            'stats': {
                'archived': Category.objects.filter(is_deleted=True).count(),
                'total_items': total_items,
            },
            'used_icons': used_icons,
        })


class CategoryDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Category.objects.filter(is_deleted=False).annotate(
            items_count=Count('items', filter=Q(items__is_deleted=False))
        )


class CategorySoftDeleteView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        cat = get_object_or_404(Category, pk=pk, is_deleted=False)
        cat.is_deleted, cat.is_active = True, False
        cat.save(update_fields=['is_deleted', 'is_active', 'updated_at'])
        return Response({'message': f'Category "{cat.name}" soft-deleted.'})


# ==========================================
# ITEM VIEWS (Admin)
# ==========================================

class AdminItemListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        status_filter = self.request.query_params.get('status', 'all')
        if status_filter == 'deleted':
            qs = Item.objects.filter(is_deleted=True)
        elif status_filter == 'published':
            qs = Item.objects.filter(is_deleted=False, is_published=True)
        elif status_filter == 'unpublished':
            qs = Item.objects.filter(is_deleted=False, is_published=False)
        else:  # 'all'
            qs = Item.objects.filter(is_deleted=False)

        if category_id := self.request.query_params.get('category'):
            if category_id.isdigit():
                qs = qs.filter(category_id=int(category_id))

        if search := self.request.query_params.get('search'):
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(slug__icontains=search))

        sort = self.request.query_params.get('sort', '-created_at')
        allowed_sorts = {'-created_at', 'created_at', 'name', '-name', 'rental_price', '-rental_price', 'stock', '-stock'}
        return qs.select_related('category', 'owner').prefetch_related('images').order_by(sort if sort in allowed_sorts else '-created_at')

    def get(self, request):
        qs = self.get_queryset()
        page_num = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))

        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page_num)

        stats = {
            'total': Item.objects.filter(is_deleted=False).count(),
            'published': Item.objects.filter(is_deleted=False, is_published=True).count(),
            'unpublished': Item.objects.filter(is_deleted=False, is_published=False).count(),
            'deleted': Item.objects.filter(is_deleted=True).count(),
        }

        return Response({
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'results': ItemSerializer(page_obj.object_list, many=True, context={'request': request}).data,
            'stats': stats,
        })

    def post(self, request):
        serializer = ItemSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save(owner=request.user)

        # Process multiple uploaded images with Pillow
        raw_files = request.FILES.getlist('images')
        try:
            primary_idx = int(request.data.get('primary_image_index', 0))
        except (ValueError, TypeError):
            primary_idx = 0

        for idx, f in enumerate(raw_files):
            processed_file = process_item_image(f)
            ItemImage.objects.create(
                item=item,
                image=processed_file,
                is_primary=(idx == primary_idx)
            )

        # If files were uploaded but none marked primary, mark the first one
        if raw_files and not item.images.filter(is_primary=True).exists():
            first_img = item.images.first()
            if first_img:
                first_img.is_primary = True
                first_img.save(update_fields=['is_primary'])

        return Response(ItemSerializer(item, context={'request': request}).data, status=status.HTTP_201_CREATED)


class AdminItemDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get_object(self, pk):
        return get_object_or_404(Item.objects.select_related('category', 'owner').prefetch_related('images'), pk=pk)

    def get(self, request, pk):
        item = self.get_object(pk)
        return Response(ItemSerializer(item, context={'request': request}).data)

    def patch(self, request, pk):
        item = self.get_object(pk)
        serializer = ItemSerializer(item, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # Handle deletion of specific existing images
        delete_ids = request.data.get('delete_image_ids')
        if delete_ids:
            if isinstance(delete_ids, str):
                try:
                    delete_ids = json.loads(delete_ids)
                except Exception:
                    delete_ids = [int(i.strip()) for i in delete_ids.split(',') if i.strip().isdigit()]
            if isinstance(delete_ids, list):
                item.images.filter(id__in=delete_ids).delete()

        # Handle newly uploaded images with Pillow
        raw_files = request.FILES.getlist('images')
        for f in raw_files:
            processed_file = process_item_image(f)
            ItemImage.objects.create(item=item, image=processed_file, is_primary=False)

        # Handle primary image selection
        primary_id = request.data.get('primary_image_id')
        if primary_id:
            try:
                primary_id = int(primary_id)
                item.images.update(is_primary=False)
                item.images.filter(id=primary_id).update(is_primary=True)
            except (ValueError, TypeError):
                pass
        elif not item.images.filter(is_primary=True).exists() and item.images.exists():
            first_img = item.images.first()
            first_img.is_primary = True
            first_img.save(update_fields=['is_primary'])

        return Response(ItemSerializer(item, context={'request': request}).data)


class AdminItemSoftDeleteView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk, is_deleted=False)
        item.is_deleted = True
        item.is_published = False
        item.save(update_fields=['is_deleted', 'is_published', 'updated_at'])
        return Response({'message': f'Item "{item.name}" soft-deleted successfully.'})


# ==========================================
# PUBLIC ITEM VIEWS (Customer Frontend)
# ==========================================

class PublicItemListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Item.objects.filter(is_deleted=False, is_published=True).select_related('category', 'owner').prefetch_related('images')

        if category_id := request.query_params.get('category'):
            if category_id.isdigit():
                qs = qs.filter(category_id=int(category_id))

        if search := request.query_params.get('search'):
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))

        sort = request.query_params.get('sort', '-created_at')
        allowed_sorts = {'-created_at', 'created_at', 'name', 'rental_price', '-rental_price'}
        qs = qs.order_by(sort if sort in allowed_sorts else '-created_at')

        page_num = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 12))
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page_num)

        return Response({
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'results': ItemSerializer(page_obj.object_list, many=True, context={'request': request}).data,
        })


class PublicItemDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        item = get_object_or_404(
            Item.objects.select_related('category', 'owner').prefetch_related('images'),
            pk=pk,
            is_deleted=False,
            is_published=True
        )
        return Response(ItemSerializer(item, context={'request': request}).data)
