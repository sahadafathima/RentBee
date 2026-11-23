from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Address
from .serializers import AddressSerializer
from users.permissions import IsActiveUser


class AddressListCreateView(generics.ListCreateAPIView):
    """List all saved addresses for the authenticated user, or create a new address."""
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get_queryset(self):
        return Address.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a specific address belonging to the user."""
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get_queryset(self):
        return Address.objects.filter(
            user=self.request.user
        )
