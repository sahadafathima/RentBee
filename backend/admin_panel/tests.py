from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import Category, Item, ItemImage
from bookings.models import Booking, IssueReport
from bookings.services import get_item_availability

User = get_user_model()


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="admin@rentbee.com",
            password="AdminPassword123!",
            full_name="Admin Staff",
            phone_number="9990001110",
        )
        self.customer = User.objects.create_user(
            email="customer@rentbee.com",
            password="CustomerPassword123!",
            full_name="Customer User",
            phone_number="9990001111",
            is_active=True,
            is_email_verified=True,
        )

    def test_unauthenticated_cannot_access_admin_endpoints(self):
        res = self.client.get("/api/admin/users/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_forbidden(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.get("/api/admin/users/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_and_search_users(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/admin/users/?search=customer")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "customer@rentbee.com")

    def test_admin_can_block_and_unblock_user(self):
        self.client.force_authenticate(user=self.admin)

        # Block user
        block_res = self.client.patch(
            f"/api/admin/users/{self.customer.id}/status/",
            {"action": "block"},
            format="json",
        )
        self.assertEqual(block_res.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

        # Unblock user
        unblock_res = self.client.patch(
            f"/api/admin/users/{self.customer.id}/status/",
            {"action": "unblock"},
            format="json",
        )
        self.assertEqual(unblock_res.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)


class AdminBookingAndInventoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="admin_booking@rentbee.com",
            password="AdminPassword123!",
            full_name="Admin Staff",
            phone_number="9990002220",
        )
        self.renter = User.objects.create_user(
            email="renter_booking@rentbee.com",
            password="CustomerPassword123!",
            full_name="Renter Booking",
            phone_number="9990002221",
        )
        self.owner = User.objects.create_user(
            email="owner_booking@rentbee.com",
            password="OwnerPassword123!",
            full_name="Owner Booking",
            phone_number="9990002222",
        )
        self.category = Category.objects.create(name="Sports Gear", icon="⚽", is_active=True)
        self.item = Item.objects.create(
            name="Professional Tennis Racket",
            category=self.category,
            owner=self.owner,
            rental_price=Decimal("500.00"),
            deposit=Decimal("1000.00"),
            stock=2,
            is_published=True,
        )

        today = timezone.localdate()
        self.booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal("500.00"),
            rental_amount=Decimal("1000.00"),
            deposit_amount=Decimal("1000.00"),
            total_amount=Decimal("2000.00"),
            status='pending_approval',
            payment_status='pending',
            payment_method='online',
        )

    def test_admin_can_list_and_filter_bookings(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/admin/bookings/?status=pending_approval")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data.get("count"), 1)
        self.assertEqual(res.data["results"][0]["booking_reference"], self.booking.booking_reference)

    def test_admin_booking_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/admin/bookings/{self.booking.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.booking.id)
        self.assertEqual(res.data["item"]["name"], self.item.name)

    def test_approve_booking_reserves_stock_and_rejects_insufficient_stock(self):
        self.client.force_authenticate(user=self.admin)
        # Approve booking
        res = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/status/",
            {"target_status": "waiting_for_pickup"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "waiting_for_pickup")

        # Second booking requesting 2 units for overlapping dates (total stock is 2, 1 already reserved)
        today = timezone.localdate()
        booking2 = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            requested_quantity=2,
            daily_price=Decimal("500.00"),
            rental_amount=Decimal("2000.00"),
            deposit_amount=Decimal("1000.00"),
            total_amount=Decimal("3000.00"),
            status='pending_approval',
        )
        # Attempting to approve booking2 must fail due to insufficient stock
        res_fail = self.client.post(
            f"/api/admin/bookings/{booking2.id}/status/",
            {"target_status": "waiting_for_pickup"},
            format="json",
        )
        self.assertEqual(res_fail.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only 1 unit(s) are available", res_fail.data.get("error", ""))

    def test_safeguard_1_pickup_blocked_without_payment(self):
        self.client.force_authenticate(user=self.admin)
        self.booking.status = "waiting_for_pickup"
        self.booking.payment_status = "pending"
        self.booking.save()

        # Pickup without payment must fail
        res = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/status/",
            {"target_status": "rental_in_progress"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("until payment is verified", res.data.get("error", ""))

        # Verify payment, now pickup must succeed
        self.booking.payment_status = "paid"
        self.booking.save()
        res_ok = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/status/",
            {"target_status": "rental_in_progress"},
            format="json",
        )
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "rental_in_progress")
        self.assertIsNotNone(self.booking.picked_up_at)
        self.assertIsNotNone(self.booking.return_deadline)

    def test_safeguard_2_return_acceptance_and_rejection(self):
        self.client.force_authenticate(user=self.admin)
        self.booking.status = "rental_in_progress"
        self.booking.picked_up_at = timezone.now()
        self.booking.save()

        # Reject return without reason must fail
        res_no_reason = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/return-action/",
            {"action": "reject", "reason": ""},
            format="json",
        )
        self.assertEqual(res_no_reason.status_code, status.HTTP_400_BAD_REQUEST)

        # Reject return with reason creates issue report and keeps rental in progress
        res_reject = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/return-action/",
            {"action": "reject", "reason": "Racket strings torn, repair needed."},
            format="json",
        )
        self.assertEqual(res_reject.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "rental_in_progress")
        self.assertEqual(IssueReport.objects.filter(booking=self.booking).count(), 1)

        # Accept return completes rental and sets returned_at
        res_accept = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/return-action/",
            {"action": "accept"},
            format="json",
        )
        self.assertEqual(res_accept.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "completed")
        self.assertIsNotNone(self.booking.returned_at)

    def test_safeguard_3_terminal_state_idempotency(self):
        self.client.force_authenticate(user=self.admin)
        self.booking.status = "completed"
        self.booking.returned_at = timezone.now()
        self.booking.save()

        # Repeated return / transition calls return 400 without corrupting stock
        res = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/status/",
            {"target_status": "completed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("terminal", res.data.get("error", ""))

    def test_safeguard_4_prevent_reducing_stock_below_active_reservations(self):
        self.client.force_authenticate(user=self.admin)
        self.booking.status = "rental_in_progress"
        self.booking.picked_up_at = timezone.now()
        self.booking.save()  # 1 unit reserved

        # Item has stock = 2. Reducing to 1 is allowed
        res_ok = self.client.patch(
            f"/api/admin/inventory/{self.item.id}/stock/",
            {"stock": 1},
            format="json",
        )
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 1)

        # Reducing to 0 while 1 unit is in active rental MUST FAIL
        res_blocked = self.client.patch(
            f"/api/admin/inventory/{self.item.id}/stock/",
            {"stock": 0},
            format="json",
        )
        self.assertEqual(res_blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("committed to active rentals", res_blocked.data.get("error", ""))
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 1)  # Stock untouched

    def test_return_acceptance_fails_for_pending_and_pickup_states(self):
        """1. Return acceptance must return HTTP 400 for bookings in pending_approval and waiting_for_pickup."""
        self.client.force_authenticate(user=self.admin)

        # Case A: Booking in pending_approval
        self.booking.status = "pending_approval"
        self.booking.save()
        res_pending = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/return-action/",
            {"action": "accept"},
            format="json",
        )
        self.assertEqual(res_pending.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rentals in progress", res_pending.data.get("error", "").lower())

        # Case B: Booking in waiting_for_pickup
        self.booking.status = "waiting_for_pickup"
        self.booking.save()
        res_pickup = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/return-action/",
            {"action": "accept"},
            format="json",
        )
        self.assertEqual(res_pickup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rentals in progress", res_pickup.data.get("error", "").lower())

    def test_owner_can_confirm_return_after_admin_rejects_return(self):
        """2. After Admin rejects a return and creates an IssueReport, the owner must still be able to use ConfirmReturnView."""
        self.client.force_authenticate(user=self.admin)
        self.booking.status = "rental_in_progress"
        self.booking.picked_up_at = timezone.now()
        self.booking.save()

        # Admin rejects return with reason
        res_reject = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/return-action/",
            {"action": "reject", "reason": "Scratch detected on racket frame"},
            format="json",
        )
        self.assertEqual(res_reject.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "rental_in_progress")
        self.assertTrue(IssueReport.objects.filter(booking=self.booking, status="open").exists())

        # Now authenticate as the item owner and confirm physical return
        self.client.force_authenticate(user=self.owner)
        res_owner_return = self.client.post(
            f"/api/bookings/{self.booking.id}/confirm-return/",
            format="json",
        )
        self.assertEqual(res_owner_return.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "completed")
        self.assertIsNotNone(self.booking.returned_at)

    def test_pending_cancellation_preserves_stock_and_pickup_cancellation_releases_once(self):
        """3. Pending booking cancellation must not change available stock. Cancelling waiting_for_pickup must release reserved quantity exactly once."""
        self.client.force_authenticate(user=self.admin)
        today = timezone.localdate()

        # Baseline: item.stock = 2, pending booking does not hold stock
        self.booking.status = "pending_approval"
        self.booking.save()
        avail_before = get_item_availability(self.item, self.booking.start_date, self.booking.end_date)
        self.assertEqual(avail_before["available_stock"], 2)

        # Cancel pending booking -> available stock must remain 2
        res_cancel_pending = self.client.post(
            f"/api/admin/bookings/{self.booking.id}/status/",
            {"target_status": "cancelled", "reason": "Renter changed plans"},
            format="json",
        )
        self.assertEqual(res_cancel_pending.status_code, status.HTTP_200_OK)
        avail_after_pending = get_item_availability(self.item, self.booking.start_date, self.booking.end_date)
        self.assertEqual(avail_after_pending["available_stock"], 2)

        # Now create an approved booking holding 1 reserved unit
        pickup_booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal("500.00"),
            rental_amount=Decimal("1000.00"),
            deposit_amount=Decimal("1000.00"),
            total_amount=Decimal("2000.00"),
            status="waiting_for_pickup",
            payment_status="paid",
        )
        avail_with_reservation = get_item_availability(self.item, pickup_booking.start_date, pickup_booking.end_date)
        self.assertEqual(avail_with_reservation["available_stock"], 1)

        # Cancel waiting_for_pickup booking -> releases 1 unit back to available
        res_cancel_pickup = self.client.post(
            f"/api/admin/bookings/{pickup_booking.id}/status/",
            {"target_status": "cancelled", "reason": "Logistics issue"},
            format="json",
        )
        self.assertEqual(res_cancel_pickup.status_code, status.HTTP_200_OK)
        avail_after_pickup_cancel = get_item_availability(self.item, pickup_booking.start_date, pickup_booking.end_date)
        self.assertEqual(avail_after_pickup_cancel["available_stock"], 2)

        # Repeating cancel must fail (idempotent, terminal state) and available stock remains 2
        res_repeat_cancel = self.client.post(
            f"/api/admin/bookings/{pickup_booking.id}/status/",
            {"target_status": "cancelled"},
            format="json",
        )
        self.assertEqual(res_repeat_cancel.status_code, status.HTTP_400_BAD_REQUEST)
        avail_final = get_item_availability(self.item, pickup_booking.start_date, pickup_booking.end_date)
        self.assertEqual(avail_final["available_stock"], 2)

    def test_multiple_overlapping_bookings_peak_reservation_calculation(self):
        """4. Multiple overlapping active bookings must be handled correctly when calculating peak reservations during stock editing."""
        self.client.force_authenticate(user=self.admin)
        self.item.stock = 5
        self.item.save()

        today = timezone.localdate()
        # Booking A: Day 1 to Day 3, qty=2
        Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=1), end_date=today + timedelta(days=3),
            duration_days=2, requested_quantity=2, daily_price=Decimal("500.00"),
            rental_amount=Decimal("1000.00"), deposit_amount=Decimal("1000.00"), total_amount=Decimal("2000.00"),
            status="waiting_for_pickup", payment_status="paid"
        )
        # Booking B: Day 2 to Day 4, qty=2 (Overlaps A on Day 2 and 3 => Peak overlap = 2 + 2 = 4)
        Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=2), end_date=today + timedelta(days=4),
            duration_days=2, requested_quantity=2, daily_price=Decimal("500.00"),
            rental_amount=Decimal("1000.00"), deposit_amount=Decimal("1000.00"), total_amount=Decimal("2000.00"),
            status="waiting_for_pickup", payment_status="paid"
        )
        # Booking C: Day 5 to Day 6, qty=3 (Disjoint interval, peak on days 5-6 is 3)
        Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=5), end_date=today + timedelta(days=6),
            duration_days=1, requested_quantity=3, daily_price=Decimal("500.00"),
            rental_amount=Decimal("500.00"), deposit_amount=Decimal("1000.00"), total_amount=Decimal("1500.00"),
            status="waiting_for_pickup", payment_status="paid"
        )

        # Overall sweep-line peak is 4 (on Day 2-3).
        # Reducing stock to 3 must fail with 400
        res_fail_3 = self.client.patch(
            f"/api/admin/inventory/{self.item.id}/stock/",
            {"stock": 3},
            format="json",
        )
        self.assertEqual(res_fail_3.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("4 unit(s) are currently committed", res_fail_3.data.get("error", ""))

        # Reducing stock to 4 must succeed (matches peak)
        res_ok_4 = self.client.patch(
            f"/api/admin/inventory/{self.item.id}/stock/",
            {"stock": 4},
            format="json",
        )
        self.assertEqual(res_ok_4.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 4)

        # Increasing stock to 6 must succeed
        res_ok_6 = self.client.patch(
            f"/api/admin/inventory/{self.item.id}/stock/",
            {"stock": 6},
            format="json",
        )
        self.assertEqual(res_ok_6.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 6)

    def test_pickup_blocked_for_all_non_paid_payment_statuses(self):
        """5. Pickup confirmation must be blocked for payment_status values pending, failed, and refunded."""
        self.client.force_authenticate(user=self.admin)
        self.booking.status = "waiting_for_pickup"

        for non_paid_status in ["pending", "failed", "refunded"]:
            self.booking.payment_status = non_paid_status
            self.booking.save()

            res = self.client.post(
                f"/api/admin/bookings/{self.booking.id}/status/",
                {"target_status": "rental_in_progress"},
                format="json",
            )
            self.assertEqual(
                res.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected HTTP 400 for payment_status '{non_paid_status}' but got {res.status_code}"
            )
            self.assertIn("until payment is verified", res.data.get("error", ""))
            self.booking.refresh_from_db()
            self.assertEqual(self.booking.status, "waiting_for_pickup")

    def test_admin_booking_and_inventory_endpoints_enforce_authentication_and_admin_permissions(self):
        """6. Both Admin Booking and Admin Inventory endpoints must reject unauthenticated (401) and non-admin (403)."""
        endpoints = [
            ("GET", "/api/admin/bookings/"),
            ("GET", f"/api/admin/bookings/{self.booking.id}/"),
            ("POST", f"/api/admin/bookings/{self.booking.id}/status/", {"target_status": "cancelled"}),
            ("POST", f"/api/admin/bookings/{self.booking.id}/return-action/", {"action": "accept"}),
            ("GET", "/api/admin/inventory/"),
            ("PATCH", f"/api/admin/inventory/{self.item.id}/stock/", {"stock": 5}),
        ]

        # 1. Unauthenticated users must receive HTTP 401
        self.client.logout()
        for method, url, *body in endpoints:
            payload = body[0] if body else {}
            if method == "GET":
                res = self.client.get(url)
            elif method == "POST":
                res = self.client.post(url, payload, format="json")
            elif method == "PATCH":
                res = self.client.patch(url, payload, format="json")
            self.assertEqual(
                res.status_code,
                status.HTTP_401_UNAUTHORIZED,
                f"Expected 401 for unauthenticated {method} {url}, got {res.status_code}"
            )

        # 2. Authenticated non-admin customer must receive HTTP 403
        self.client.force_authenticate(user=self.renter)
        for method, url, *body in endpoints:
            payload = body[0] if body else {}
            if method == "GET":
                res = self.client.get(url)
            elif method == "POST":
                res = self.client.post(url, payload, format="json")
            elif method == "PATCH":
                res = self.client.patch(url, payload, format="json")
            self.assertEqual(
                res.status_code,
                status.HTTP_403_FORBIDDEN,
                f"Expected 403 for non-admin {method} {url}, got {res.status_code}"
            )

    def test_product_wise_total_booking_count_in_admin_search(self):
        """Verifies product-wise total booking count in Admin Booking Management search."""
        self.client.force_authenticate(user=self.admin)
        today = timezone.localdate()

        # Item A: Canon Camera with 3 bookings across diverse statuses and quantities
        canon = Item.objects.create(
            name="Canon EOS R5 Mirrorless Camera",
            category=self.category,
            owner=self.owner,
            rental_price=Decimal("1500.00"),
            stock=5,
            is_published=True,
        )
        # Booking 1: pending_approval, qty=2
        Booking.objects.create(
            renter=self.renter, item=canon, owner=self.owner,
            start_date=today + timedelta(days=1), end_date=today + timedelta(days=2),
            duration_days=1, requested_quantity=2, daily_price=Decimal("1500.00"),
            rental_amount=Decimal("3000.00"), deposit_amount=Decimal("0.00"), total_amount=Decimal("3000.00"),
            status='pending_approval'
        )
        # Booking 2: rental_in_progress, qty=3
        Booking.objects.create(
            renter=self.renter, item=canon, owner=self.owner,
            start_date=today + timedelta(days=3), end_date=today + timedelta(days=4),
            duration_days=1, requested_quantity=3, daily_price=Decimal("1500.00"),
            rental_amount=Decimal("4500.00"), deposit_amount=Decimal("0.00"), total_amount=Decimal("4500.00"),
            status='rental_in_progress'
        )
        # Booking 3: cancelled, qty=1
        Booking.objects.create(
            renter=self.renter, item=canon, owner=self.owner,
            start_date=today + timedelta(days=5), end_date=today + timedelta(days=6),
            duration_days=1, requested_quantity=1, daily_price=Decimal("1500.00"),
            rental_amount=Decimal("1500.00"), deposit_amount=Decimal("0.00"), total_amount=Decimal("1500.00"),
            status='cancelled'
        )

        # Item B: Laptop with 2 bookings
        laptop = Item.objects.create(
            name="Dell XPS Developer Laptop",
            category=self.category,
            owner=self.owner,
            rental_price=Decimal("1200.00"),
            stock=3,
            is_published=True,
        )
        Booking.objects.create(
            renter=self.renter, item=laptop, owner=self.owner,
            start_date=today + timedelta(days=1), end_date=today + timedelta(days=2),
            duration_days=1, requested_quantity=1, daily_price=Decimal("1200.00"),
            rental_amount=Decimal("1200.00"), deposit_amount=Decimal("0.00"), total_amount=Decimal("1200.00"),
            status='waiting_for_pickup'
        )
        Booking.objects.create(
            renter=self.renter, item=laptop, owner=self.owner,
            start_date=today + timedelta(days=3), end_date=today + timedelta(days=4),
            duration_days=1, requested_quantity=1, daily_price=Decimal("1200.00"),
            rental_amount=Decimal("1200.00"), deposit_amount=Decimal("0.00"), total_amount=Decimal("1200.00"),
            status='completed'
        )

        # Item C: Projector with 0 bookings
        Item.objects.create(
            name="Epson Home Cinema Projector",
            category=self.category,
            owner=self.owner,
            rental_price=Decimal("800.00"),
            stock=2,
            is_published=True,
        )

        # 1. Search for Canon -> must report exactly 3 bookings (counting records, not units which would be 6)
        res_canon = self.client.get("/api/admin/bookings/?search=Canon")
        self.assertEqual(res_canon.status_code, status.HTTP_200_OK)
        summaries_canon = res_canon.data.get("product_summaries", [])
        self.assertTrue(len(summaries_canon) >= 1)
        canon_summary = next((s for s in summaries_canon if s["id"] == canon.id), None)
        self.assertIsNotNone(canon_summary)
        self.assertEqual(canon_summary["name"], canon.name)
        self.assertEqual(canon_summary["total_bookings"], 3)  # Exactly 3 records
        # Table rows also have total_bookings_count attached
        for b in res_canon.data.get("results", []):
            if b.get("item") and b["item"]["id"] == canon.id:
                self.assertEqual(b["item"]["total_bookings_count"], 3)

        # 2. Search for Laptop -> must report exactly 2 bookings
        res_laptop = self.client.get("/api/admin/bookings/?search=Laptop")
        self.assertEqual(res_laptop.status_code, status.HTTP_200_OK)
        summaries_laptop = res_laptop.data.get("product_summaries", [])
        laptop_summary = next((s for s in summaries_laptop if s["id"] == laptop.id), None)
        self.assertIsNotNone(laptop_summary)
        self.assertEqual(laptop_summary["total_bookings"], 2)

        # 3. Search for Projector -> must report 0 bookings
        res_proj = self.client.get("/api/admin/bookings/?search=Projector")
        self.assertEqual(res_proj.status_code, status.HTTP_200_OK)
        summaries_proj = res_proj.data.get("product_summaries", [])
        proj_summary = next((s for s in summaries_proj if "Projector" in s["name"]), None)
        self.assertIsNotNone(proj_summary)
        self.assertEqual(proj_summary["total_bookings"], 0)

        # 4. Search matching multiple products (e.g. "Camera" matches Canon and Sony)
        sony_camera = Item.objects.create(
            name="Sony Alpha Mirrorless Camera",
            category=self.category,
            owner=self.owner,
            rental_price=Decimal("1800.00"),
            stock=4,
            is_published=True,
        )
        Booking.objects.create(
            renter=self.renter, item=sony_camera, owner=self.owner,
            start_date=today + timedelta(days=2), end_date=today + timedelta(days=3),
            duration_days=1, requested_quantity=1, daily_price=Decimal("1800.00"),
            rental_amount=Decimal("1800.00"), deposit_amount=Decimal("0.00"), total_amount=Decimal("1800.00"),
            status='completed'
        )
        res_cameras = self.client.get("/api/admin/bookings/?search=Camera")
        self.assertEqual(res_cameras.status_code, status.HTTP_200_OK)
        summaries_cam = res_cameras.data.get("product_summaries", [])
        cam_ids = [s["id"] for s in summaries_cam]
        self.assertIn(canon.id, cam_ids)
        self.assertIn(sony_camera.id, cam_ids)
        c_item = next(s for s in summaries_cam if s["id"] == canon.id)
        s_item = next(s for s in summaries_cam if s["id"] == sony_camera.id)
        self.assertEqual(c_item["total_bookings"], 3)
        self.assertEqual(s_item["total_bookings"], 1)

        # 5. When search is cleared / empty, product_summaries must be empty
        res_no_search = self.client.get("/api/admin/bookings/")
        self.assertEqual(res_no_search.status_code, status.HTTP_200_OK)
        self.assertEqual(res_no_search.data.get("product_summaries"), [])

    def test_admin_inventory_list_returns_correct_item_image_urls(self):
        """Verifies that Admin Inventory serializer correctly returns item image URLs and handles items without images."""
        self.client.force_authenticate(user=self.admin)

        # 1. Attach primary image to item
        ItemImage.objects.create(
            item=self.item,
            image="item_images/sample_racket.jpg",
            is_primary=True,
        )

        # 2. Create another item without image
        no_img_item = Item.objects.create(
            name="Generic Tool Set Without Photo",
            category=self.category,
            owner=self.owner,
            rental_price=Decimal("300.00"),
            stock=4,
            is_published=True,
        )

        res = self.client.get("/api/admin/inventory/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", [])

        # Item with image must have non-null primary_image_url and primary_image
        racket_data = next((i for i in results if i["id"] == self.item.id), None)
        self.assertIsNotNone(racket_data)
        self.assertIsNotNone(racket_data.get("primary_image_url"))
        self.assertIn("item_images/sample_racket.jpg", racket_data["primary_image_url"])
        self.assertEqual(racket_data.get("primary_image"), racket_data["primary_image_url"])
        # Verify actual rental price and security deposit values are returned accurately
        self.assertEqual(Decimal(str(racket_data.get("rental_price"))), Decimal("500.00"))
        self.assertEqual(Decimal(str(racket_data.get("deposit"))), Decimal("1000.00"))
        self.assertEqual(Decimal(str(racket_data.get("price_per_day"))), Decimal("500.00"))
        self.assertEqual(Decimal(str(racket_data.get("security_deposit"))), Decimal("1000.00"))

        # Item without image must return None for both fields
        no_img_data = next((i for i in results if i["id"] == no_img_item.id), None)
        self.assertIsNotNone(no_img_data)
        self.assertIsNone(no_img_data.get("primary_image_url"))
        self.assertIsNone(no_img_data.get("primary_image"))

    def test_admin_inventory_owner_details_different_users(self):
        """Verifies that products belonging to different users display their correct respective owner full name and email."""
        self.client.force_authenticate(user=self.admin)

        # Owner 1 (self.owner already has full_name="Owner Booking", email="owner_booking@rentbee.com")
        # Owner 2: Distinct user with first_name and last_name
        owner_2 = User.objects.create_user(
            email="aarav.host@rentbee.com",
            password="HostPassword123!",
            first_name="Aarav",
            last_name="Sharma",
            full_name="Aarav Sharma",
            phone_number="9990003333",
        )
        item_2 = Item.objects.create(
            name="Professional Cinema Camera",
            category=self.category,
            owner=owner_2,
            rental_price=Decimal("1200.00"),
            deposit=Decimal("5000.00"),
            stock=3,
            is_published=True,
        )

        # Owner 3: User without full_name (fallback to username / email prefix)
        owner_3 = User.objects.create_user(
            email="priya.tech@rentbee.com",
            password="HostPassword123!",
            full_name="",
            phone_number="9990004444",
        )
        item_3 = Item.objects.create(
            name="Audio Interface Studio Kit",
            category=self.category,
            owner=owner_3,
            rental_price=Decimal("600.00"),
            deposit=Decimal("1500.00"),
            stock=2,
            is_published=True,
        )

        # Item without owner
        item_no_owner = Item.objects.create(
            name="Unassigned Inventory Equipment",
            category=self.category,
            owner=None,
            rental_price=Decimal("200.00"),
            deposit=Decimal("500.00"),
            stock=1,
            is_published=True,
        )

        res = self.client.get("/api/admin/inventory/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", [])

        # 1. Verify Item 1 (owned by self.owner)
        data_1 = next((i for i in results if i["id"] == self.item.id), None)
        self.assertIsNotNone(data_1)
        self.assertEqual(data_1["owner"]["full_name"], "Owner Booking")
        self.assertEqual(data_1["owner"]["email"], "owner_booking@rentbee.com")
        self.assertEqual(data_1["owner_name"], "Owner Booking")
        self.assertEqual(data_1["owner_email"], "owner_booking@rentbee.com")
        self.assertNotEqual(data_1["owner"]["full_name"], "RentBee Official")
        self.assertNotEqual(data_1["owner"]["email"], "admin@rentbee.local")

        # 2. Verify Item 2 (owned by owner_2: Aarav Sharma)
        data_2 = next((i for i in results if i["id"] == item_2.id), None)
        self.assertIsNotNone(data_2)
        self.assertEqual(data_2["owner"]["full_name"], "Aarav Sharma")
        self.assertEqual(data_2["owner"]["email"], "aarav.host@rentbee.com")
        self.assertEqual(data_2["owner_name"], "Aarav Sharma")
        self.assertEqual(data_2["owner_email"], "aarav.host@rentbee.com")
        self.assertNotEqual(data_2["owner"]["full_name"], "RentBee Official")

        # 3. Verify Item 3 (owned by owner_3: fallback to username/email prefix)
        data_3 = next((i for i in results if i["id"] == item_3.id), None)
        self.assertIsNotNone(data_3)
        self.assertEqual(data_3["owner"]["full_name"], "priya.tech")
        self.assertEqual(data_3["owner"]["email"], "priya.tech@rentbee.com")

        # 4. Verify Item without owner returns None (not fake RentBee Official)
        data_none = next((i for i in results if i["id"] == item_no_owner.id), None)
        self.assertIsNotNone(data_none)
        self.assertIsNone(data_none.get("owner"))
        self.assertIsNone(data_none.get("owner_name"))
        self.assertIsNone(data_none.get("owner_email"))

