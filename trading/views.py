# views.py
import asyncio
import aiohttp
import json
import logging
from decimal import Decimal
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Avg, Sum, Max, Min, Q, Count
from django.db.models.functions import TruncDay, TruncMonth
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import generics

from .models import *
from .serializers import *

from utils.helper import *

class TradingAccountView(generics.ListAPIView):
    permission_classes=[IsAuthenticated]
    serializer_class = MT5UserSerializer

    def get_queryset(self):
        user = self.request.user
        q = MT5User.objects.filter(user=user).order_by('-selected_date')
        return q
    
class SelectAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, login):
        user = self.request.user
        acc = get_object_or_404(MT5User, login=login, user=user)
        acc.selected_date = timezone.now()
        acc.save()

        q = MT5User.objects.filter(user=user).order_by('-selected_date')
        data = MT5UserSerializer(q, many=True).data
        return Response(data, status=status.HTTP_200_OK)
    

class PositionView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class= MT5PositionSerializer

    def get_queryset(self):
        login = self.kwargs.get('login', None)
        if login and login.isdigit():
            return MT5Position.objects.filter(login=login)
        return MT5Position.objects.none()
    

class AccountStatsView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AccountStatSerializer

    def get_object(self):
        login = self.kwargs.get('login', None)
        print("LOGIN", login)
        if login and login.isdigit():
            return MT5Account.objects.get(login=login)
        return None
    
class DailySummaryView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DailySummary

    def get_queryset(self):
        login = self.kwargs.get('login', None)
        if login and login.isdigit():
            return MT5Daily.objects.filter(login=login)
        return MT5Daily.objects.none()