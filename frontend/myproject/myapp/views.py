from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from .models import Students
from. serializers import StudentsSerializer

# Create your views here.

class Studentsviewset(ModelViewSet):
    queryset=Students.objects.all()
    serializer_class= StudentsSerializer
