from django.shortcuts import render
from django.contrib.auth import get_user_model
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction
from asgiref.sync import async_to_sync

from .serializers import *
from utils.filters import *

User = get_user_model()

class PropFirmChallengeListView(generics.ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PropFirmChallengeSerializer
    queryset = PropFirmChallenge.objects.all()
    filterset_class = PropFirmChallengeFilter
    filter_backends = [DjangoFilterBackend]

class PropFirmChallengeDetailView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PropFirmChallengeSerializer
    queryset = PropFirmChallenge.objects.all()
    lookup_field = 'id'

class BalanceListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        challenges = PropFirmChallenge.objects.order_by('account_size')
        skill_check = list(
           challenges.filter(challenge_class='skill_check').values_list('account_size', flat=True)
        )
        challenge = list(
           challenges.filter(challenge_class='challenge').values_list('account_size', flat=True)
        )
        return Response({
            'skill_check': skill_check,
            'challenge': challenge
        }, status=status.HTTP_200_OK)
# Create your views here.
