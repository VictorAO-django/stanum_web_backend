# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

urlpatterns = [
    # ViewSet URLs
    path('accounts', TradingAccountView.as_view()),
    path('account/select/<int:id>', SelectAccountView.as_view()),
    path('accounts/<int:account_id>/stats', AccountStatsView.as_view(), name='account-stats'),

]