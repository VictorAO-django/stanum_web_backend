"""
URL configuration for vermittlungsbot project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from .views import *
from django.urls import path

urlpatterns = [
    path('auth/login', LoginView.as_view()),
    path('users', UserListView.as_view()),
    path('users/<str:id>', UserDetailView.as_view()),
    path('users/<str:id>/delete', DeleteUserView.as_view()),
    path('users/<str:id>/kyc', UserKYCView.as_view()),
    path('users/<str:id>/kyc/id/action', ProofOfIDActionView.as_view()),
    path('users/<str:id>/kyc/address1/action', ProofOfAddress1ActionView.as_view()),
    path('users/<str:id>/kyc/address2/action', ProofOfAddress2ActionView.as_view()),

    path('users/<str:id>/wallet', UserWalletView.as_view()),
    path('users/<str:id>/wallet/transactions', UserWalletTransactionView.as_view()),

    path('challenges', ChallengeListView.as_view()),
    path('challenges/create/', ChallengeCreateView.as_view()),
    path('challenges/<str:id>/', ChallengeDetailView.as_view()),

    path('payouts', PayoutsView.as_view()),
    path('payouts/<str:id>/accept', ApprovePayoutView.as_view()),
    path('payouts/<str:id>/ipn', ApprovePayoutView.as_view()),
    path('payouts/<str:id>/reject', RejectPayoutView.as_view()),
    
    path('ticket', TicketListCreateAPIView.as_view()),
    path('ticket/<str:ticket_id>/messages', MessageListCreateAPIView.as_view()),
    path('ticket/<str:ticket_id>/close', CloseTicketApiView.as_view())
]