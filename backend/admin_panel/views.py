
from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import status

from users.models import User

from .permissions import IsAdminUser
from .serializers import AdminUserSerializer

# Search, Filter and Pagination

class AdminUserListView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):

        users = User.objects.filter(
            is_staff=False,
            is_superuser=False
        )

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
            user = User.objects.get(
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
            user = User.objects.get(
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
