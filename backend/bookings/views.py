from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Item
from .models import Booking, IssueReport, AvailabilityNotificationRequest, InAppNotification, PushSubscription
from .push_service import get_vapid_public_key, send_web_push
from .serializers import (
    BookingCreateSerializer,
    BookingDetailSerializer,
    BookingListSerializer,
    IssueReportSerializer,
    AvailabilityNotificationRequestSerializer,
    InAppNotificationSerializer,
)
from .services import (
    expire_stale_pending_bookings,
    get_item_availability,
    locked_booking_transition,
    notify_booking_event,
    process_availability_notifications_for_item,
)


class MyBookingsListView(APIView):
    """
    Renter's My Bookings dashboard endpoint.
    Returns dynamic status counts, search across item & owner, tab filtering, and pagination.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Opportunistic just-in-time expiry
        expire_stale_pending_bookings()

        user = request.user
        base_qs = Booking.objects.filter(renter=user).select_related(
            'item', 'item__category', 'owner', 'owner__profile'
        ).prefetch_related('item__images')

        # Dynamic counts across all user bookings
        counts = {
            'all': base_qs.count(),
            'incoming': base_qs.filter(status='pending_approval').count(),
            'accepted': base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress']).count(),
            'active': base_qs.filter(status__in=['pending_approval', 'waiting_for_pickup', 'rental_in_progress']).count(),
            'rejected': base_qs.filter(status='rejected').count(),
            'completed': base_qs.filter(status='completed').count(),
            'cancelled': base_qs.filter(status__in=['cancelled', 'rejected', 'expired']).count(),
        }

        tab = request.query_params.get('tab', 'all').lower()
        if tab in ['incoming', 'pending']:
            qs = base_qs.filter(status='pending_approval')
        elif tab == 'accepted':
            qs = base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress'])
        elif tab == 'active':
            qs = base_qs.filter(status__in=['pending_approval', 'waiting_for_pickup', 'rental_in_progress'])
        elif tab == 'rejected':
            qs = base_qs.filter(status='rejected')
        elif tab == 'completed':
            qs = base_qs.filter(status='completed')
        elif tab == 'cancelled':
            qs = base_qs.filter(status__in=['cancelled', 'rejected', 'expired'])
        else:
            qs = base_qs

        # Backend search by item name or owner name
        if search := request.query_params.get('search'):
            search = search.strip()
            if search:
                qs = qs.filter(
                    Q(item__name__icontains=search) |
                    Q(owner__full_name__icontains=search) |
                    Q(owner__email__icontains=search) |
                    Q(booking_reference__icontains=search)
                )

        try:
            page_num = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page_num = 1

        try:
            page_size = max(1, min(100, int(request.query_params.get('page_size', 6))))
        except (ValueError, TypeError):
            page_size = 6

        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page_num)

        serializer = BookingListSerializer(page_obj.object_list, many=True, context={'request': request})

        return Response({
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'counts': counts,
            'results': serializer.data,
        })


class BookingCreateView(APIView):
    """
    Renter creates a new booking request.
    Calculates prices on backend, checks availability & row-locking, snapshots owner and prices.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        expire_stale_pending_bookings()
        serializer = BookingCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        detail_serializer = BookingDetailSerializer(booking, context={'request': request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class BookingDetailView(APIView):
    """
    Complete booking details endpoint.
    Strict privacy: only authorized participants (renter, owner, staff) can access.
    Owner pickup address is redacted during pending_approval.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        expire_stale_pending_bookings()

        booking = get_object_or_404(
            Booking.objects.select_related(
                'item', 'item__category', 'owner', 'owner__profile', 'renter'
            ).prefetch_related('item__images', 'owner__addresses', 'issue_reports'),
            pk=pk
        )

        # Participant Authorization Check
        is_participant = (
            booking.renter_id == request.user.id or
            booking.owner_id == request.user.id or
            request.user.is_staff
        )
        if not is_participant:
            return Response(
                {'error': 'You do not have permission to view this booking.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = BookingDetailSerializer(booking, context={'request': request})
        return Response(serializer.data)


class CancelBookingView(APIView):
    """
    Renter cancellation endpoint.
    Allowed strictly before pickup (during pending_approval or waiting_for_pickup).
    Strictly forbidden during rental_in_progress or completed.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.renter_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the booking renter can cancel this booking.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status in ['rental_in_progress', 'completed']:
            return Response(
                {'error': 'Cannot cancel a rental that is already in progress or completed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if booking.status in ['cancelled', 'rejected', 'expired']:
            return Response(
                {'error': f'Booking is already {booking.get_status_display().lower()}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', '').strip()
        booking.status = 'cancelled'
        booking.cancelled_at = timezone.now()
        booking.cancelled_by = request.user
        booking.cancellation_reason = reason
        booking.save(update_fields=['status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at'])

        # Notify users who requested availability notifications for this item
        process_availability_notifications_for_item(booking.item_id)

        return Response({
            'message': 'Booking cancelled successfully.',
            'booking_id': booking.id,
            'status': booking.status
        })


class OwnerApproveBookingView(APIView):
    """
    Item owner approves a pending booking request.
    Moves status from pending_approval to waiting_for_pickup.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.owner_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the item owner can approve this booking request.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'pending_approval':
            return Response(
                {'error': f'Cannot approve booking with current status: {booking.get_status_display()}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        availability = get_item_availability(booking.item, booking.start_date, booking.end_date)
        if booking.requested_quantity > availability['available_stock']:
            return Response(
                {'requested_quantity':
                 f'Requested quantity is unavailable. Only {availability["available_stock"]} items are currently available for these dates.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        booking.status = 'waiting_for_pickup'
        booking.approved_at = timezone.now()
        booking.save(update_fields=['status', 'approved_at', 'updated_at'])
        notify_booking_event(booking, 'accepted')

        return Response({
            'message': 'Booking request approved. Now waiting for pickup.',
            'booking_id': booking.id,
            'status': booking.status
        })


class OwnerRejectBookingView(APIView):
    """
    Item owner declines a pending booking request.
    Moves status from pending_approval to rejected.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.owner_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the item owner can decline this booking request.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'pending_approval':
            return Response(
                {'error': f'Cannot decline booking with current status: {booking.get_status_display()}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', '').strip()
        booking.status = 'rejected'
        booking.rejected_at = timezone.now()
        booking.rejection_reason = reason
        booking.cancelled_by = request.user
        booking.save(update_fields=['status', 'rejected_at', 'rejection_reason', 'cancelled_by', 'updated_at'])
        notify_booking_event(booking, 'rejected')

        # Notify users who requested availability notifications for this item
        process_availability_notifications_for_item(booking.item_id)

        return Response({
            'message': 'Booking request declined.',
            'booking_id': booking.id,
            'status': booking.status
        })


class ConfirmPickupView(APIView):
    """
    Item owner confirms handover of the item to renter.
    Moves status from waiting_for_pickup to rental_in_progress.
    Strictly blocked if backend payment verification is pending.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.owner_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the item owner can confirm item pickup.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'waiting_for_pickup':
            return Response(
                {'error': f'Cannot confirm pickup for booking in "{booking.get_status_display()}" state.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Payment Verification Check
        if not booking.is_payment_verified():
            return Response(
                {'error': 'Pickup cannot be confirmed until payment is verified by the platform.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        booking.status = 'rental_in_progress'
        booking.picked_up_at = timezone.now()
        booking.save(update_fields=['status', 'picked_up_at', 'updated_at'])

        return Response({
            'message': 'Pickup confirmed. Rental is now in progress.',
            'booking_id': booking.id,
            'status': booking.status
        })


class ConfirmReturnView(APIView):
    """
    Item owner confirms physical return of the item.
    Moves status from rental_in_progress to completed.
    Never triggers automatically.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.owner_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the item owner can confirm item return.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'rental_in_progress':
            return Response(
                {'error': f'Cannot confirm return for booking in "{booking.get_status_display()}" state.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        booking.status = 'completed'
        booking.returned_at = timezone.now()
        booking.save(update_fields=['status', 'returned_at', 'updated_at'])
        process_availability_notifications_for_item(booking.item_id)

        return Response({
            'message': 'Rental completed successfully.',
            'booking_id': booking.id,
            'status': booking.status
        })


class ReportProblemView(APIView):
    """
    Renter reports an issue with their rental.
    Strictly restricted to rental_in_progress only.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.renter_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the renter can report a problem for this booking.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'rental_in_progress':
            return Response(
                {'error': 'Problem reports can only be submitted while a rental is in progress.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        description = request.data.get('description', '').strip()
        if not description:
            return Response(
                {'description': ['Problem description is required.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        report = IssueReport.objects.create(
            booking=booking,
            renter=request.user,
            owner=booking.owner,
            description=description,
            status='open'
        )

        serializer = IssueReportSerializer(report, context={'request': request})
        return Response({
            'message': 'Problem reported successfully. The owner and platform support have been notified.',
            'report': serializer.data
        }, status=status.HTTP_201_CREATED)


class HostBookingsListView(APIView):
    """
    Owner's Host Hub endpoint for incoming requests and active rentals.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        expire_stale_pending_bookings()

        user = request.user
        base_qs = Booking.objects.filter(owner=user).select_related(
            'item', 'item__category', 'renter'
        ).prefetch_related('item__images')

        tab = request.query_params.get('tab', 'all').lower()
        if tab == 'incoming':
            qs = base_qs.filter(status='pending_approval')
        elif tab in ['accepted', 'active']:
            qs = base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress'])
        elif tab == 'rejected':
            qs = base_qs.filter(status='rejected')
        elif tab == 'completed':
            qs = base_qs.filter(status='completed')
        else:
            qs = base_qs

        counts = {
            'all': base_qs.count(),
            'incoming': base_qs.filter(status='pending_approval').count(),
            'accepted': base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress']).count(),
            'active': base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress']).count(),
            'rejected': base_qs.filter(status='rejected').count(),
            'completed': base_qs.filter(status='completed').count(),
        }

        serializer = BookingListSerializer(qs, many=True, context={'request': request})
        return Response({
            'counts': counts,
            'results': serializer.data
        })


class HostReportsListView(APIView):
    """
    Endpoint for viewing issues reported on user's bookings (as host or renter).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        reports = IssueReport.objects.filter(
            Q(owner=user) | Q(renter=user)
        ).select_related(
            'booking', 'booking__item', 'renter', 'owner'
        ).distinct()
        serializer = IssueReportSerializer(reports, many=True, context={'request': request})
        return Response(serializer.data)


class CheckAvailabilityView(APIView):
    """
    Real-time check whether an item is available for a given date range.
    Returns { is_available, status_label, message, conflicting_count }.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        expire_stale_pending_bookings()

        item_id = request.query_params.get('item_id')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not item_id:
            return Response({'error': 'item_id query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not start_date_str or not end_date_str:
            return Response({'error': 'start_date and end_date query parameters are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid item_id.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Expected YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()
        if start_date < today:
            return Response({
                'is_available': False,
                'status_label': 'Past Date',
                'message': 'Rental start date cannot be in the past.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if end_date <= start_date:
            return Response({
                'is_available': False,
                'status_label': 'Invalid Dates',
                'message': 'End date must be after start date.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = Item.objects.get(pk=item_id)
        except Item.DoesNotExist:
            return Response({'error': 'Item not found.'}, status=status.HTTP_404_NOT_FOUND)

        availability = get_item_availability(item, start_date, end_date)
        requested_quantity = request.query_params.get('requested_quantity')
        requested_quantity_available = None
        if requested_quantity is not None:
            try:
                requested_quantity = int(requested_quantity)
                if requested_quantity < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'error': 'requested_quantity must be a positive integer.'}, status=status.HTTP_400_BAD_REQUEST)
            requested_quantity_available = requested_quantity <= availability['available_stock']
        message = (
            'Item is available for these dates.' if availability['is_available']
            else 'This item is already booked, reserved, or out of stock for the selected dates.'
        )
        if requested_quantity is not None and not requested_quantity_available:
            message = f'Requested quantity is unavailable. Only {availability["available_stock"]} items are currently available for these dates.'
        return Response({
            **availability,
            'status_label': ('Available' if availability['is_available'] else
                             'Booked' if availability['availability_reason'] == 'reserved' else 'Unavailable'),
            'message': message,
            'conflicting_count': max(0, availability['total_stock'] - availability['available_stock']),
            **({'requested_quantity': requested_quantity,
                'is_requested_quantity_available': requested_quantity_available}
               if requested_quantity is not None else {}),
        })


class NotifyAvailabilityView(APIView):
    """
    Renter requests to be notified if an item becomes available for given dates.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_id = request.data.get('item_id')
        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')

        if not item_id or not start_date_str or not end_date_str:
            return Response({'error': 'item_id, start_date, and end_date are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item_id = int(item_id)
            start_date = timezone.datetime.strptime(str(start_date_str), '%Y-%m-%d').date()
            end_date = timezone.datetime.strptime(str(end_date_str), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response({'error': 'Invalid item_id or date format (expected YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()
        if start_date < today:
            return Response({'error': 'Rental start date cannot be in the past.'}, status=status.HTTP_400_BAD_REQUEST)

        if end_date <= start_date:
            return Response({'error': 'End date must be after start date.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = Item.objects.get(pk=item_id)
        except Item.DoesNotExist:
            return Response({'error': 'Item not found.'}, status=status.HTTP_404_NOT_FOUND)

        req_obj, created = AvailabilityNotificationRequest.objects.get_or_create(
            user=request.user,
            item=item,
            start_date=start_date,
            end_date=end_date,
            defaults={'is_notified': False}
        )
        if not created and req_obj.is_notified:
            req_obj.is_notified = False
            req_obj.save(update_fields=['is_notified'])

        return Response({
            'message': 'You will be notified as soon as these dates become available.',
            'id': req_obj.id,
            'item_id': item.id,
            'item_name': item.name,
            'start_date': str(start_date),
            'end_date': str(end_date),
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class NotificationsListView(APIView):
    """
    List in-app notifications for the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = InAppNotification.objects.filter(user=request.user).select_related('booking__item', 'item').order_by('-created_at')
        unread_count = InAppNotification.objects.filter(user=request.user, is_read=False).count()
        serializer = InAppNotificationSerializer(notifications, many=True, context={'request': request})
        return Response({
            'unread_count': unread_count,
            'results': serializer.data
        })


class MarkNotificationReadView(APIView):
    """
    Mark a specific notification as read.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(InAppNotification, pk=pk, user=request.user)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({
            'message': 'Notification marked as read.',
            'id': notification.id
        })


class MarkAllNotificationsReadView(APIView):
    """
    Mark all notifications as read for the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        InAppNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'All notifications marked as read.'})


class PushVapidKeyView(APIView):
    """
    Returns the VAPID public key for web push subscription.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'public_key': get_vapid_public_key()})


class PushSubscribeView(APIView):
    """
    Saves or updates a Web Push subscription for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        endpoint = request.data.get('endpoint', '').strip()
        keys = request.data.get('keys', {})
        p256dh = keys.get('p256dh', '').strip() if isinstance(keys, dict) else ''
        auth = keys.get('auth', '').strip() if isinstance(keys, dict) else ''

        if not endpoint or not p256dh or not auth:
            return Response(
                {'error': 'Invalid subscription data. endpoint, keys.p256dh and keys.auth are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        sub, created = PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={
                'p256dh': p256dh,
                'auth': auth,
                'user_agent': user_agent,
            }
        )

        return Response({
            'message': 'Push subscription saved successfully.',
            'created': created,
            'id': sub.id
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PushUnsubscribeView(APIView):
    """
    Removes a Web Push subscription for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        endpoint = request.data.get('endpoint', '').strip()
        if endpoint:
            PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        else:
            PushSubscription.objects.filter(user=request.user).delete()

        return Response({'message': 'Push subscription removed successfully.'})


class PushTestView(APIView):
    """
    Sends a test web push notification to the authenticated user's registered devices.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = send_web_push(
            request.user,
            title='RentBee Test',
            body='Web push notification is working successfully!',
            data={'url': '/host-hub', 'type': 'test'}
        )
        return Response({
            'message': f'Test push notification dispatched to {count} active device(s).',
            'devices_notified': count
        })



