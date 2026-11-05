from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Address
from .serializers import AddressSerializer
from users.permissions import IsActiveUser


class AddressListCreateView(generics.ListCreateAPIView):

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated , IsActiveUser]

    def get_queryset(self):
        return Address.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    def perform_create(self, serializer):
        existing_address = self.get_queryset().first()

        if existing_address:
            serializer.instance = existing_address
            serializer.save(user=self.request.user)
        else:
            serializer.save(user=self.request.user)