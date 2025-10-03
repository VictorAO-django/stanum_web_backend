from django.shortcuts import render, get_object_or_404
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
    queryset = PropFirmChallenge.objects.filter(competition=None).exclude(challenge_class__in=['skill_check_funding', 'challenge_funding'])
    filterset_class = PropFirmChallengeFilter
    filter_backends = [DjangoFilterBackend]

class PropFirmChallengeDetailView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PropFirmChallengeSerializer
    queryset = PropFirmChallenge.objects.filter(competition=None).exclude(challenge_class__in=['skill_check_funding', 'challenge_funding'])
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


class ChallengeCertificateView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class=ChallengeCertificateSerializer
    
    def get_queryset(self):
        user = self.request.user
        return ChallengeCertificate.objects.filter(user=user)
    
class IsAParticipantView(APIView):
    def get(self, request, uuid, *args, **kwargs):
        user = request.user
        ctx = get_object_or_404(Competition, uuid=uuid)
        mt5_users = MT5User.objects.filter(user=user)
        if not mt5_users.exists():
            return Response({"status": False}, status=status.HTTP_200_OK)

        in_challenge = False
        for i in mt5_users:
            if i.competition == ctx:
                in_challenge = True
        
        return Response({"status":in_challenge}, status=status.HTTP_200_OK)
                


class CompetitionView(generics.RetrieveAPIView):
    permission_classes=[AllowAny]
    serializer_class=CompetitionSerializer
    
    def get_object(self):
        id=self.kwargs.get('uuid', 0)
        return get_object_or_404(Competition, uuid=id)


class CompetitionResultView(generics.ListAPIView):
    permission_classes=[IsAuthenticated]
    serializer_class=CompetitionResultSerializer
    
    def get_queryset(self):
        uuid = self.kwargs.get("uuid")
        return CompetitionResult.objects.filter(competition_uuid=uuid).order_by('rank')