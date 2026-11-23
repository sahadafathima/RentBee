
from datetime import timedelta
from django.db.models import Q, Count
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import status

from users.models import User
from catalog.models import Item
from bookings.models import Booking, IssueReport, InAppNotification
from bookings.serializers import BookingDetailSerializer
from bookings.services import (
    get_item_availability,
    locked_booking_transition,
    process_availability_notifications_for_item,
    expire_stale_pending_bookings,
)

from .permissions import IsAdminUser
from .serializers import AdminUserSerializer, AdminInventoryItemSerializer

# Search, Filter and Pagination

class AdminUserListView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):

        users = User.objects.filter(
            is_staff=False,
            is_superuser=False
        ).prefetch_related('addresses')

        # Search by name, email or phone number
        search = request.query_params.get("search", "").strip()

        if search:
            users = users.filter(
                Q(full_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            )

        # Filter active or blocked users
        user_status = request.query_params.get("status")

        if user_status == "active":
            users = users.filter(is_active=True)

        elif user_status == "blocked":
            users = users.filter(is_active=False)

        elif user_status:
            return Response(
                {"error": "Invalid status. Use active or blocked."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Filter email verification
        email_verified = request.query_params.get("email_verified")

        if email_verified == "true":
            users = users.filter(is_email_verified=True)

        elif email_verified == "false":
            users = users.filter(is_email_verified=False)

        elif email_verified:
            return Response(
                {"error": "Invalid email_verified value."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Filter phone verification
        phone_verified = request.query_params.get("phone_verified")

        if phone_verified == "true":
            users = users.filter(is_phone_verified=True)

        elif phone_verified == "false":
            users = users.filter(is_phone_verified=False)

        elif phone_verified:
            return Response(
                {"error": "Invalid phone_verified value."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Latest registered users first
        users = users.order_by("-created_at", "-id")

        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10

        paginated_users = paginator.paginate_queryset(
            users,
            request,
            view=self
        )

        serializer = AdminUserSerializer(
            paginated_users,
            many=True
        )

        return paginator.get_paginated_response(serializer.data)


class AdminUserDetailView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, pk):

        try:
            user = User.objects.prefetch_related('addresses').get(
                pk=pk,
                is_staff=False,
                is_superuser=False
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AdminUserSerializer(user)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

# 3. Admin Block / Unblock User API

class AdminUserBlockView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, pk):

        try:
            user = User.objects.prefetch_related('addresses').get(
                pk=pk,
                is_staff=False,
                is_superuser=False
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        action = request.data.get("action")

        if action == "block":

            if not user.is_active:
                return Response(
                    {"message": "User is already blocked."},
                    status=status.HTTP_200_OK
                )

            user.is_active = False
            user.save(update_fields=["is_active"])

            return Response(
                {"message": "User blocked successfully."},
                status=status.HTTP_200_OK
            )

        elif action == "unblock":

            if user.is_active:
                return Response(
                    {"message": "User is already active."},
                    status=status.HTTP_200_OK
                )

            user.is_active = True
            user.save(update_fields=["is_active"])

            return Response(
                {"message": "User unblocked successfully."},
                status=status.HTTP_200_OK
            )

        return Response(
            {"error": "Invalid action. Use block or unblock."},
            status=status.HTTP_400_BAD_REQUEST
        )


# ==============================================================================
# Admin Booking Management Views
# ==============================================================================

class AdminBookingListView(APIView):
    """
    Lists all platform bookings for administrators.
    Supports multi-field search, status/payment/date filters, sorting, and pagination.
    Newest bookings first by default.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        expire_stale_pending_bookings()

        qs = Booking.objects.select_related(
            'item', 'item__category', 'owner', 'renter', 'renter_address'
        ).prefetch_related('item__images', 'issue_reports')

        # Multi-field search
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(booking_reference__icontains=search) |
                Q(renter__email__icontains=search) |
                Q(renter__full_name__icontains=search) |
                Q(renter__phone_number__icontains=search) |
                Q(item__name__icontains=search) |
                Q(owner__email__icontains=search) |
                Q(owner__full_name__icontains=search)
            )

        # Tab shortcut
        tab = request.query_params.get('tab', '').strip()
        if tab == 'pending':
            qs = qs.filter(status='pending_approval')
        elif tab == 'pickup':
            qs = qs.filter(status='waiting_for_pickup')
        elif tab == 'active':
            qs = qs.filter(status='rental_in_progress')
        elif tab == 'completed':
            qs = qs.filter(status='completed')
        elif tab == 'cancelled':
            qs = qs.filter(status='cancelled')
        elif tab == 'rejected':
            qs = qs.filter(status='rejected')
        elif tab == 'return_requests':
            # Active rentals under return review / inspection
            qs = qs.filter(status='rental_in_progress')

        # Filter by booking status
        b_status = request.query_params.get('status', '').strip()
        if b_status:
            qs = qs.filter(status=b_status)

        # Filter by payment status
        p_status = request.query_params.get('payment_status', '').strip()
        if p_status:
            qs = qs.filter(payment_status=p_status)

        # Filter by rental dates
        start_date = request.query_params.get('start_date', '').strip()
        if start_date:
            qs = qs.filter(start_date__gte=start_date)

        end_date = request.query_params.get('end_date', '').strip()
        if end_date:
            qs = qs.filter(end_date__lte=end_date)

        # Filter by booking creation date
        created_after = request.query_params.get('created_after', '').strip()
        if created_after:
            qs = qs.filter(created_at__date__gte=created_after)

        created_before = request.query_params.get('created_before', '').strip()
        if created_before:
            qs = qs.filter(created_at__date__lte=created_before)

        # Sorting
        sort = request.query_params.get('sort', '-created_at').strip()
        allowed_sorts = {
            '-created_at', 'created_at',
            '-total_amount', 'total_amount',
            '-start_date', 'start_date'
        }
        if sort not in allowed_sorts:
            sort = '-created_at'
        qs = qs.order_by(sort, '-id')

        # Counts summary for tabs
        counts = {
            'all': Booking.objects.count(),
            'pending': Booking.objects.filter(status='pending_approval').count(),
            'pickup': Booking.objects.filter(status='waiting_for_pickup').count(),
            'active': Booking.objects.filter(status='rental_in_progress').count(),
            'completed': Booking.objects.filter(status='completed').count(),
            'cancelled': Booking.objects.filter(status='cancelled').count(),
            'rejected': Booking.objects.filter(status='rejected').count(),
            'return_requests': Booking.objects.filter(status='rental_in_progress').count(),
        }

        # Pagination
        paginator = PageNumberPagination()
        try:
            page_size = int(request.query_params.get('page_size', 10))
            paginator.page_size = min(max(page_size, 1), 100)
        except (ValueError, TypeError):
            paginator.page_size = 10

        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = BookingDetailSerializer(page, many=True, context={'request': request})

        # Product-wise total booking count for matching searched items
        product_summaries = []
        if search:
            matched_item_ids = list(
                Item.objects.filter(name__icontains=search, is_deleted=False).values_list('id', flat=True)[:25]
            )
            booking_item_ids = list(qs.values_list('item_id', flat=True).distinct()[:25])
            all_target_ids = list(dict.fromkeys(matched_item_ids + booking_item_ids))

            if all_target_ids:
                items_for_summary = (
                    Item.objects.filter(id__in=all_target_ids, is_deleted=False)
                    .select_related('category')
                    .prefetch_related('images')
                )
                # Count ALL booking records for each specific item across all statuses, counted once
                b_counts = {
                    row['item_id']: row['total']
                    for row in Booking.objects.filter(item_id__in=all_target_ids)
                    .values('item_id')
                    .annotate(total=Count('id'))
                }
                for itm in items_for_summary:
                    img = itm.images.filter(is_primary=True).first() or itm.images.first()
                    img_url = request.build_absolute_uri(img.image.url) if (img and img.image) else None
                    product_summaries.append({
                        'id': itm.id,
                        'name': itm.name,
                        'category_name': itm.category.name if itm.category else '',
                        'primary_image_url': img_url,
                        'total_bookings': b_counts.get(itm.id, 0),
                    })

        # Also populate total_bookings_count on item object for each booking row
        page_item_ids = [b['item']['id'] for b in serializer.data if b.get('item') and b['item'].get('id')]
        if page_item_ids:
            page_counts = {
                row['item_id']: row['total']
                for row in Booking.objects.filter(item_id__in=page_item_ids)
                .values('item_id')
                .annotate(total=Count('id'))
            }
            for b in serializer.data:
                if b.get('item') and b['item'].get('id'):
                    b['item']['total_bookings_count'] = page_counts.get(b['item']['id'], 0)

        response = paginator.get_paginated_response(serializer.data)
        response.data['counts'] = counts
        response.data['product_summaries'] = product_summaries
        response.data['total_pages'] = paginator.page.paginator.num_pages
        return response


class AdminBookingDetailView(APIView):
    """
    Retrieves full details for a single booking in the admin panel.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, pk):
        expire_stale_pending_bookings()
        booking = get_object_or_404(
            Booking.objects.select_related(
                'item', 'item__category', 'owner', 'owner__profile', 'renter', 'renter_address'
            ).prefetch_related('item__images', 'owner__addresses', 'issue_reports'),
            pk=pk
        )
        serializer = BookingDetailSerializer(booking, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminBookingStatusTransitionView(APIView):
    """
    Safely transitions booking statuses with strict backend validation.
    Preserves owner pickup confirmation and payment integrity (Safeguard 1).
    Idempotent and atomic to protect stock allocations (Safeguard 3).
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        target_status = request.data.get('target_status', '').strip()
        reason = request.data.get('reason', '').strip()

        if not target_status:
            return Response({'error': 'target_status is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Terminal state check
        if booking.status in ['completed', 'cancelled', 'rejected', 'expired']:
            return Response(
                {'error': f'Booking is in terminal "{booking.get_status_display()}" state and cannot be modified.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------------------------
        # Transition: from pending_approval
        # ----------------------------------------------------------------------
        if booking.status == 'pending_approval':
            if target_status == 'waiting_for_pickup':
                # Check stock availability
                avail = get_item_availability(booking.item, booking.start_date, booking.end_date)
                if booking.requested_quantity > avail['available_stock']:
                    return Response({
                        'error': f'Cannot approve booking. Only {avail["available_stock"]} unit(s) are available for these dates.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                booking.status = 'waiting_for_pickup'
                booking.approved_at = timezone.now()
                booking.save(update_fields=['status', 'approved_at', 'updated_at'])
                return Response({
                    'message': 'Booking approved successfully. Stock reserved.',
                    'booking': BookingDetailSerializer(booking, context={'request': request}).data
                })

            elif target_status == 'rejected':
                if not reason:
                    return Response({'error': 'A rejection reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
                booking.status = 'rejected'
                booking.rejected_at = timezone.now()
                booking.rejection_reason = reason
                booking.save(update_fields=['status', 'rejected_at', 'rejection_reason', 'updated_at'])
                return Response({
                    'message': 'Booking request declined.',
                    'booking': BookingDetailSerializer(booking, context={'request': request}).data
                })

            elif target_status == 'cancelled':
                booking.status = 'cancelled'
                booking.cancelled_at = timezone.now()
                booking.cancelled_by = request.user
                booking.cancellation_reason = reason or 'Cancelled by Administrator'
                booking.save(update_fields=['status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at'])
                return Response({
                    'message': 'Booking cancelled.',
                    'booking': BookingDetailSerializer(booking, context={'request': request}).data
                })

            else:
                return Response(
                    {'error': f'Invalid transition from pending_approval to {target_status}.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ----------------------------------------------------------------------
        # Transition: from waiting_for_pickup
        # ----------------------------------------------------------------------
        elif booking.status == 'waiting_for_pickup':
            if target_status == 'rental_in_progress':
                # SAFEGUARD 1: Strict payment verification check
                if not booking.is_payment_verified():
                    return Response({
                        'error': 'Pickup cannot be confirmed until payment is verified by the platform.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                booking.status = 'rental_in_progress'
                booking.picked_up_at = timezone.now()
                booking.save(update_fields=['status', 'picked_up_at', 'updated_at'])
                return Response({
                    'message': 'Pickup confirmed. Rental is now in progress.',
                    'booking': BookingDetailSerializer(booking, context={'request': request}).data
                })

            elif target_status == 'cancelled':
                booking.status = 'cancelled'
                booking.cancelled_at = timezone.now()
                booking.cancelled_by = request.user
                booking.cancellation_reason = reason or 'Cancelled by Administrator'
                booking.save(update_fields=['status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at'])
                # Stock is automatically released
                process_availability_notifications_for_item(booking.item_id)
                return Response({
                    'message': 'Booking cancelled. Reserved stock released.',
                    'booking': BookingDetailSerializer(booking, context={'request': request}).data
                })

            else:
                return Response(
                    {'error': f'Invalid transition from waiting_for_pickup to {target_status}.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ----------------------------------------------------------------------
        # Transition: from rental_in_progress
        # ----------------------------------------------------------------------
        elif booking.status == 'rental_in_progress':
            if target_status == 'completed':
                booking.status = 'completed'
                booking.returned_at = timezone.now()
                booking.save(update_fields=['status', 'returned_at', 'updated_at'])
                # Stock is automatically released
                process_availability_notifications_for_item(booking.item_id)
                return Response({
                    'message': 'Rental completed successfully. Stock restored.',
                    'booking': BookingDetailSerializer(booking, context={'request': request}).data
                })
            else:
                return Response(
                    {'error': f'Invalid transition from rental_in_progress to {target_status}.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response({'error': 'Invalid booking state.'}, status=status.HTTP_400_BAD_REQUEST)


class AdminReturnActionView(APIView):
    """
    Manages rental return requests and reviews (Safeguard 2).
    - 'accept': Completes the rental, stamps returned_at, restores stock, resolves open issues.
    - 'reject': Requires non-empty reason, creates an IssueReport, and keeps rental active without conflict.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.status != 'rental_in_progress':
            return Response(
                {'error': f'Return actions can only be performed on rentals in progress (current status: {booking.get_status_display()}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        action = request.data.get('action', '').strip().lower()
        reason = request.data.get('reason', '').strip()

        if action == 'accept':
            booking.status = 'completed'
            booking.returned_at = timezone.now()
            booking.save(update_fields=['status', 'returned_at', 'updated_at'])

            # Mark any open issues as resolved
            booking.issue_reports.filter(status='open').update(status='resolved')

            # Notify availability
            process_availability_notifications_for_item(booking.item_id)

            return Response({
                'message': 'Return confirmed and accepted. Rental marked as Completed.',
                'booking': BookingDetailSerializer(booking, context={'request': request}).data
            }, status=status.HTTP_200_OK)

        elif action == 'reject':
            if not reason:
                return Response(
                    {'error': 'A detailed reason is mandatory when rejecting a return request.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Safeguard 2: Log issue report so owner and renter have clear record
            report = IssueReport.objects.create(
                booking=booking,
                renter=booking.renter,
                owner=booking.owner,
                description=f'Return Inspection Rejected by Admin: {reason}',
                status='open'
            )

            # In-app notification to renter
            InAppNotification.objects.create(
                user=booking.renter,
                title='Return Request Rejected',
                message=f'Your return request for {booking.item.name} was rejected. Reason: {reason}',
                item=booking.item
            )

            return Response({
                'message': 'Return request rejected. An issue dispute has been logged and the rental remains active.',
                'issue_report_id': report.id,
                'booking': BookingDetailSerializer(booking, context={'request': request}).data
            }, status=status.HTTP_200_OK)

        return Response(
            {'error': 'Invalid action. Must be "accept" or "reject".'},
            status=status.HTTP_400_BAD_REQUEST
        )


# ==============================================================================
# Admin Inventory Management Views
# ==============================================================================

class AdminInventoryListView(APIView):
    """
    Provides stock and inventory statistics across catalog items for administrators.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        qs = Item.objects.filter(is_deleted=False).select_related(
            'category', 'owner'
        ).prefetch_related('images', 'bookings')

        # Search
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(category__name__icontains=search) |
                Q(owner__email__icontains=search) |
                Q(owner__full_name__icontains=search)
            )

        # Filter by stock status
        stock_filter = request.query_params.get('stock_status', '').strip()
        if stock_filter == 'out_of_stock':
            qs = qs.filter(stock=0)
        elif stock_filter == 'in_stock':
            qs = qs.filter(stock__gt=0)
        elif stock_filter == 'low_stock':
            qs = qs.filter(stock__gt=0, stock__lte=2)

        # Sorting
        sort = request.query_params.get('sort', '-created_at').strip()
        allowed_sorts = {
            '-created_at', 'created_at',
            'name', '-name',
            'stock', '-stock',
            'rental_price', '-rental_price',
            'price_per_day', '-price_per_day'
        }
        if sort not in allowed_sorts:
            sort = '-created_at'
        if sort == 'price_per_day':
            sort = 'rental_price'
        elif sort == '-price_per_day':
            sort = '-rental_price'
        qs = qs.order_by(sort, '-id')

        # Overview counts across all active catalog items
        all_items = Item.objects.filter(is_deleted=False)
        total_items_count = all_items.count()
        total_stock_units = sum(i.stock for i in all_items)
        active_rentals_units = sum(
            b.requested_quantity for b in Booking.objects.filter(
                status__in=['waiting_for_pickup', 'rental_in_progress']
            )
        )
        available_units = max(0, total_stock_units - active_rentals_units)

        # Pagination
        paginator = PageNumberPagination()
        try:
            page_size = int(request.query_params.get('page_size', 10))
            paginator.page_size = min(max(page_size, 1), 100)
        except (ValueError, TypeError):
            paginator.page_size = 10

        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = AdminInventoryItemSerializer(page, many=True, context={'request': request})

        response = paginator.get_paginated_response(serializer.data)
        response.data['metrics'] = {
            'total_items': total_items_count,
            'total_stock': total_stock_units,
            'reserved_units': active_rentals_units,
            'available_units': available_units,
        }
        response.data['total_pages'] = paginator.page.paginator.num_pages
        return response


class AdminStockUpdateView(APIView):
    """
    Atomically updates item total stock with Safeguard 4 validation:
    Prevents reducing total stock below currently active confirmed reservations.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, pk):
        try:
            new_stock = int(request.data.get('stock'))
            if new_stock < 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {'error': 'stock must be a non-negative integer (0 or greater).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            item = get_object_or_404(Item.objects.select_for_update(), pk=pk, is_deleted=False)

            # Safeguard 4: Calculate peak active reservations across active confirmed bookings
            active_bookings = Booking.objects.select_for_update().filter(
                item=item,
                status__in=['waiting_for_pickup', 'rental_in_progress']
            )

            today = timezone.localdate()
            events = {}
            for b in active_bookings.only('start_date', 'end_date', 'status', 'requested_quantity'):
                left = today if b.status == 'rental_in_progress' else max(today, b.start_date)
                right = b.end_date
                qty = max(1, b.requested_quantity)
                events[left] = events.get(left, 0) + qty
                release_date = right + timedelta(days=1)
                events[release_date] = events.get(release_date, 0) - qty

            peak_reserved = 0
            current = 0
            for day in sorted(events):
                current += events[day]
                peak_reserved = max(peak_reserved, current)

            if new_stock < peak_reserved:
                return Response({
                    'error': f'Cannot reduce total stock to {new_stock}. {peak_reserved} unit(s) are currently committed to active rentals.'
                }, status=status.HTTP_400_BAD_REQUEST)

            item.stock = new_stock
            item.save(update_fields=['stock', 'updated_at'])

            serializer = AdminInventoryItemSerializer(item, context={'request': request})
            return Response({
                'message': f'Stock updated successfully to {new_stock} units.',
                'item': serializer.data
            }, status=status.HTTP_200_OK)

