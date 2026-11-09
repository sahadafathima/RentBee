import json
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.permissions import IsAdminUser
from .image_utils import process_item_image
from .models import Category, Item, ItemImage, RentalKitItem, WishlistItem
from .serializers import CategorySerializer, ItemSerializer, WishlistItemSerializer


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
        return qs.select_related('category', 'owner').prefetch_related('images', 'rental_kit_items').order_by(sort if sort in allowed_sorts else '-created_at')

    def get(self, request):
        qs = self.get_queryset()
        try:
            page_num = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page_num = 1

        try:
            page_size = max(1, min(100, int(request.query_params.get('page_size', 10))))
        except (ValueError, TypeError):
            page_size = 10

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

        # Process rental kit entries if provided
        rental_kit_raw = request.data.get('rental_kit')
        if rental_kit_raw is not None:
            if isinstance(rental_kit_raw, str):
                try:
                    rental_kit_entries = json.loads(rental_kit_raw)
                except Exception:
                    rental_kit_entries = [x.strip() for x in rental_kit_raw.split(',') if x.strip()]
            elif isinstance(rental_kit_raw, list):
                rental_kit_entries = rental_kit_raw
            else:
                rental_kit_entries = []

            for entry in rental_kit_entries:
                if isinstance(entry, str) and entry.strip():
                    RentalKitItem.objects.create(item=item, name=entry.strip())
                elif isinstance(entry, dict) and entry.get('name', '').strip():
                    RentalKitItem.objects.create(item=item, name=entry['name'].strip())

        return Response(ItemSerializer(item, context={'request': request}).data, status=status.HTTP_201_CREATED)


class AdminItemDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get_object(self, pk):
        return get_object_or_404(Item.objects.select_related('category', 'owner').prefetch_related('images', 'rental_kit_items'), pk=pk)

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

        # Process rental kit entries if explicitly provided
        if 'rental_kit' in request.data:
            rental_kit_raw = request.data.get('rental_kit')
            if isinstance(rental_kit_raw, str):
                try:
                    rental_kit_entries = json.loads(rental_kit_raw)
                except Exception:
                    rental_kit_entries = [x.strip() for x in rental_kit_raw.split(',') if x.strip()]
            elif isinstance(rental_kit_raw, list):
                rental_kit_entries = rental_kit_raw
            else:
                rental_kit_entries = []

            item.rental_kit_items.all().delete()
            for entry in rental_kit_entries:
                if isinstance(entry, str) and entry.strip():
                    RentalKitItem.objects.create(item=item, name=entry.strip())
                elif isinstance(entry, dict) and entry.get('name', '').strip():
                    RentalKitItem.objects.create(item=item, name=entry['name'].strip())

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
        qs = Item.objects.filter(
            is_deleted=False,
            is_published=True,
            category__is_active=True,
            category__is_deleted=False
        ).filter(
            Q(owner__isnull=True) | Q(owner__is_active=True)
        ).select_related('category', 'owner').prefetch_related('images', 'owner__addresses', 'rental_kit_items')

        if category_id := request.query_params.get('category'):
            if category_id.isdigit():
                qs = qs.filter(category_id=int(category_id))

        if search := request.query_params.get('search'):
            search = search.strip()
            if search:
                qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))

        if min_price := request.query_params.get('min_price'):
            try:
                qs = qs.filter(rental_price__gte=float(min_price))
            except (ValueError, TypeError):
                pass

        if max_price := request.query_params.get('max_price'):
            try:
                qs = qs.filter(rental_price__lte=float(max_price))
            except (ValueError, TypeError):
                pass

        if owner_id := request.query_params.get('owner'):
            if owner_id.isdigit():
                qs = qs.filter(owner_id=int(owner_id))

        if exclude_id := request.query_params.get('exclude'):
            if exclude_id.isdigit():
                qs = qs.exclude(id=int(exclude_id))

        sort = request.query_params.get('sort', '-created_at')
        allowed_sorts = {'-created_at', 'rental_price', '-rental_price'}
        qs = qs.order_by(sort if sort in allowed_sorts else '-created_at')

        try:
            page_num = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page_num = 1

        try:
            page_size = max(1, min(100, int(request.query_params.get('page_size', 12))))
        except (ValueError, TypeError):
            page_size = 12

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
            Item.objects.filter(
                is_deleted=False,
                is_published=True,
                category__is_active=True,
                category__is_deleted=False
            ).filter(
                Q(owner__isnull=True) | Q(owner__is_active=True)
            ).select_related('category', 'owner').prefetch_related('images', 'owner__addresses', 'rental_kit_items'),
            pk=pk
        )
        return Response(ItemSerializer(item, context={'request': request}).data)


class PublicCategoryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        categories = Category.objects.filter(
            is_active=True,
            is_deleted=False
        ).exclude(name__iexact='all categories').exclude(icon='▦').annotate(
            items_count=Count('items', filter=Q(items__is_deleted=False, items__is_published=True))
        ).order_by('created_at', 'id')

        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data)


# ==========================================
# WISHLIST VIEWS (Authenticated Customer)
# ==========================================

class WishlistListView(APIView):
    """
    List all wishlisted items for the logged-in user, or add an item to the wishlist.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = WishlistItem.objects.filter(
            user=request.user,
            item__is_deleted=False,
            item__is_published=True,
            item__category__is_active=True,
            item__category__is_deleted=False,
        ).select_related(
            'item', 'item__category', 'item__owner'
        ).prefetch_related(
            'item__images', 'item__owner__addresses', 'item__rental_kit_items'
        )

        item_ids = list(qs.values_list('item_id', flat=True))
        serializer = WishlistItemSerializer(qs, many=True, context={'request': request})

        return Response({
            'count': qs.count(),
            'item_ids': item_ids,
            'results': serializer.data,
        })

    def post(self, request):
        item_id = request.data.get('item_id')
        if not item_id:
            return Response({'error': 'item_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid item_id.'}, status=status.HTTP_400_BAD_REQUEST)

        item = get_object_or_404(Item, pk=item_id, is_deleted=False)

        with transaction.atomic():
            wishlist_item, created = WishlistItem.objects.get_or_create(
                user=request.user,
                item=item
            )

        count = WishlistItem.objects.filter(
            user=request.user,
            item__is_deleted=False,
            item__is_published=True
        ).count()

        return Response({
            'is_wishlisted': True,
            'item_id': item.id,
            'count': count,
            'message': 'Item added to your wishlist.' if created else 'Item is already in your wishlist.'
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class WishlistToggleView(APIView):
    """
    Toggle wishlist status for a given item:
    If wishlisted -> remove it.
    If not wishlisted -> add it.
    Uses atomic transaction to safely handle rapid clicks and concurrent requests.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_id = request.data.get('item_id')
        if not item_id:
            return Response({'error': 'item_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid item_id.'}, status=status.HTTP_400_BAD_REQUEST)

        item = get_object_or_404(Item, pk=item_id, is_deleted=False)

        with transaction.atomic():
            deleted_count, _ = WishlistItem.objects.filter(user=request.user, item=item).delete()
            if deleted_count > 0:
                is_wishlisted = False
                message = 'Item removed from your wishlist.'
            else:
                try:
                    WishlistItem.objects.create(user=request.user, item=item)
                    is_wishlisted = True
                    message = 'Item added to your wishlist.'
                except IntegrityError:
                    is_wishlisted = True
                    message = 'Item is already in your wishlist.'

        count = WishlistItem.objects.filter(
            user=request.user,
            item__is_deleted=False,
            item__is_published=True
        ).count()

        return Response({
            'is_wishlisted': is_wishlisted,
            'item_id': item.id,
            'count': count,
            'message': message,
        })


class WishlistDetailView(APIView):
    """
    Remove an item from the wishlist by item_id.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, item_id):
        with transaction.atomic():
            WishlistItem.objects.filter(user=request.user, item_id=item_id).delete()

        count = WishlistItem.objects.filter(
            user=request.user,
            item__is_deleted=False,
            item__is_published=True
        ).count()

        return Response({
            'is_wishlisted': False,
            'item_id': item_id,
            'count': count,
            'message': 'Item removed from your wishlist.'
        })

