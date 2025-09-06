# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

urlpatterns = [
    # ViewSet URLs
    path('accounts', TradingAccountView.as_view()),
    path('account/select/<str:login>', SelectAccountView.as_view()),

    path('accounts/<str:login>/stats', AccountStatsView.as_view()),
    path('positions/<str:login>', PositionView.as_view()),
    path('daily-summary/<str:login>', DailySummaryView.as_view()),

    path('accounts/<str:login>/earning', AccountEarningsView.as_view()),
]   