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

from .models import (
    TradingAccount, Trade, AccountActivity, 
    DailyAccountStats, UserProfile
)
from .serializers import *

from utils.helper import *

logger = logging.getLogger(__name__)

# MetaAPI Service Configuration
METAAPI_SERVICE_URL = getattr(settings, 'METAAPI_SERVICE_URL', 'http://localhost:8001')

class MetaAPIServiceMixin:
    """Mixin for making requests to the MetaAPI FastAPI service"""
    
    async def make_metaapi_request(self, method: str, endpoint: str, data: dict = None):
        """Make async request to MetaAPI service"""
        url = f"{METAAPI_SERVICE_URL}{endpoint}"
        
        try:
            async with aiohttp.ClientSession() as session:
                if method.upper() == 'GET':
                    async with session.get(url) as response:
                        result = await response.json()
                        return result, response.status
                elif method.upper() == 'POST':
                    async with session.post(url, json=data) as response:
                        result = await response.json()
                        return result, response.status
                else:
                    raise ValueError(f"Unsupported method: {method}")
        except Exception as e:
            logger.error(f"MetaAPI service request failed: {str(e)}")
            return {'success': False, 'error': str(e)}, 500
    
    def sync_metaapi_request(self, method: str, endpoint: str, data: dict = None):
        """Synchronous wrapper for async MetaAPI requests"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            self.make_metaapi_request(method, endpoint, data)
        )


# class StandardResultsSetPagination(PageNumberPagination):
#     page_size = 20
#     page_size_query_param = 'page_size'
#     max_page_size = 100


# class UserProfileViewSet(viewsets.ModelViewSet):
#     """ViewSet for managing user trading profiles"""
#     serializer_class = UserProfileSerializer
#     permission_classes = [IsAuthenticated]
#     pagination_class = StandardResultsSetPagination
    
#     def get_queryset(self):
#         if self.request.user.is_staff:
#             return UserProfile.objects.all().select_related('user')
#         return UserProfile.objects.filter(user=self.request.user).select_related('user')
    
#     def get_object(self):
#         if self.action in ['retrieve', 'update', 'partial_update']:
#             # Users can only access their own profile unless they're staff
#             if not self.request.user.is_staff:
#                 return get_object_or_404(UserProfile, user=self.request.user)
#         return super().get_object()
    
#     @action(detail=False, methods=['get'])
#     def me(self, request):
#         """Get current user's profile"""
#         profile, created = UserProfile.objects.get_or_create(user=request.user)
#         serializer = self.get_serializer(profile)
#         return Response(serializer.data)


# class TradingAccountViewSet(viewsets.ModelViewSet, MetaAPIServiceMixin):
#     """ViewSet for managing trading accounts"""
#     serializer_class = TradingAccountSerializer
#     permission_classes = [IsAuthenticated]
#     pagination_class = StandardResultsSetPagination
    
#     def get_queryset(self):
#         queryset = TradingAccount.objects.select_related('user').prefetch_related(
#             'trades', 'activities'
#         )
        
#         if self.request.user.is_staff:
#             return queryset
#         return queryset.filter(user=self.request.user)
    
#     @action(detail=False, methods=['post'])
#     def create_account(self, request):
#         """Create a new trading account via MetaAPI service"""
#         serializer = AccountCreateRequestSerializer(
#             data=request.data, 
#             context={'request': request}
#         )
        
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
#         # Prepare data for MetaAPI service
#         metaapi_data = serializer.validated_data.copy()
#         metaapi_data['user_id'] = request.user.id
        
#         # Call MetaAPI service
#         response_data, response_status = self.sync_metaapi_request(
#             'POST', '/accounts/create', metaapi_data
#         )
        
#         if response_status != 200 or not response_data.get('success'):
#             return Response(
#                 {'error': response_data.get('message', 'Failed to create account')},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        
#         # Update user profile statistics
#         profile, _ = UserProfile.objects.get_or_create(user=request.user)
#         if serializer.validated_data['account_type'] == 'challenge':
#             profile.total_challenges_attempted += 1
#             profile.save()
        
#         return Response(response_data, status=status.HTTP_201_CREATED)
    
#     @action(detail=True, methods=['get'])
#     def real_time_status(self, request, pk=None):
#         """Get real-time account status from MetaAPI service"""
#         account = self.get_object()
        
#         response_data, response_status = self.sync_metaapi_request(
#             'GET', f'/accounts/{account.metaapi_account_id}/status'
#         )
        
#         if response_status != 200:
#             return Response(
#                 {'error': 'Failed to fetch real-time data'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        
#         # Update Django model with real-time data if successful
#         if response_data.get('success') and 'real_time' in response_data:
#             real_time_data = response_data['real_time']
#             with transaction.atomic():
#                 account.balance = Decimal(str(real_time_data.get('balance', account.balance)))
#                 account.equity = Decimal(str(real_time_data.get('equity', account.equity)))
#                 account.margin = Decimal(str(real_time_data.get('margin', 0)))
#                 account.free_margin = Decimal(str(real_time_data.get('free_margin', 0)))
#                 account.margin_level = Decimal(str(real_time_data.get('margin_level', 0)))
#                 account.updated_at = timezone.now()
#                 account.save()
        
#         serializer = AccountStatusSerializer(data=response_data)
#         if serializer.is_valid():
#             return Response(serializer.validated_data)
        
#         return Response(response_data)
    
#     @action(detail=True, methods=['get'])
#     def positions(self, request, pk=None):
#         """Get current positions for account"""
#         account = self.get_object()
        
#         response_data, response_status = self.sync_metaapi_request(
#             'GET', f'/accounts/{account.metaapi_account_id}/positions'
#         )
        
#         if response_status != 200:
#             return Response(
#                 {'error': 'Failed to fetch positions'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        
#         return Response(response_data)
    
#     @action(detail=True, methods=['post'])
#     def execute_trade(self, request, pk=None):
#         """Execute a trade on the account"""
#         account = self.get_object()
        
#         # Validate account is active
#         if not account.is_active:
#             return Response(
#                 {'error': f'Account is {account.status}'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
        
#         serializer = TradeRequestSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
#         # Prepare trade data for MetaAPI service
#         trade_data = serializer.validated_data.copy()
#         trade_data['account_id'] = account.metaapi_account_id
        
#         # Execute trade via MetaAPI service
#         response_data, response_status = self.sync_metaapi_request(
#             'POST', '/trades/execute', trade_data
#         )
        
#         if response_status != 200 or not response_data.get('success'):
#             return Response(
#                 {'error': response_data.get('message', 'Trade execution failed')},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        
#         # Log activity
#         AccountActivity.objects.create(
#             account=account,
#             activity_type='deal_executed',
#             description=f"Trade executed: {trade_data['action'].upper()} {trade_data['volume']} {trade_data['symbol']}",
#             metadata={'trade_request': trade_data, 'metaapi_response': response_data}
#         )
        
#         return Response(response_data, status=status.HTTP_201_CREATED)
    
#     @action(detail=True, methods=['post'])
#     def close_position(self, request, pk=None):
#         """Close a specific position"""
#         account = self.get_object()
#         position_id = request.data.get('position_id')
        
#         if not position_id:
#             return Response(
#                 {'error': 'position_id is required'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
        
#         response_data, response_status = self.sync_metaapi_request(
#             'POST', f'/accounts/{account.metaapi_account_id}/close-position/{position_id}'
#         )
        
#         if response_status != 200:
#             return Response(
#                 {'error': 'Failed to close position'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        
#         # Log activity
#         AccountActivity.objects.create(
#             account=account,
#             activity_type='position_closed',
#             description=f"Position {position_id} closed manually",
#             metadata={'position_id': position_id}
#         )
        
#         return Response(response_data)
    
#     @action(detail=True, methods=['post'])
#     def close_all_positions(self, request, pk=None):
#         """Close all positions for account"""
#         account = self.get_object()
        
#         response_data, response_status = self.sync_metaapi_request(
#             'POST', f'/accounts/{account.metaapi_account_id}/close-all-positions'
#         )
        
#         if response_status != 200:
#             return Response(
#                 {'error': 'Failed to close positions'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        
#         # Log activity
#         AccountActivity.objects.create(
#             account=account,
#             activity_type='position_closed',
#             description=f"All positions closed - {response_data.get('closed_count', 0)} positions",
#             metadata=response_data
#         )
        
#         return Response(response_data)
    
#     @action(detail=True, methods=['get'])
#     def equity_chart(self, request, pk=None):
#         """Get equity chart data for account"""
#         account = self.get_object()
        
#         response_data, response_status = self.sync_metaapi_request(
#             'GET', f'/accounts/{account.metaapi_account_id}/equity'
#         )
        
#         if response_status != 200:
#             return Response(
#                 {'error': 'Failed to fetch equity data'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        
#         return Response(response_data)
    
#     @action(detail=True, methods=['get'])
#     def daily_stats(self, request, pk=None):
#         """Get daily statistics for account"""
#         account = self.get_object()
        
#         # Get date range from query params
#         days = int(request.query_params.get('days', 30))
#         end_date = timezone.now().date()
#         start_date = end_date - timedelta(days=days)
        
#         stats = DailyAccountStats.objects.filter(
#             account=account,
#             date__range=[start_date, end_date]
#         ).order_by('-date')
        
#         serializer = DailyAccountStatsSerializer(stats, many=True)
#         return Response({
#             'success': True,
#             'daily_stats': serializer.data,
#             'summary': {
#                 'total_days': stats.count(),
#                 'total_trades': sum(s.trades_count for s in stats),
#                 'total_pnl': sum(s.daily_pnl for s in stats),
#                 'avg_daily_pnl': sum(s.daily_pnl for s in stats) / max(stats.count(), 1),
#                 'best_day': max(stats, key=lambda s: s.daily_pnl, default=None),
#                 'worst_day': min(stats, key=lambda s: s.daily_pnl, default=None),
#             }
#         })


# class TradeViewSet(viewsets.ReadOnlyModelViewSet):
#     """ViewSet for viewing trades"""
#     serializer_class = TradeSerializer
#     permission_classes = [IsAuthenticated]
#     pagination_class = StandardResultsSetPagination
    
#     def get_queryset(self):
#         queryset = Trade.objects.select_related('account', 'account__user')
        
#         if not self.request.user.is_staff:
#             queryset = queryset.filter(account__user=self.request.user)
        
#         # Filter by account if specified
#         account_id = self.request.query_params.get('account_id')
#         if account_id:
#             queryset = queryset.filter(account_id=account_id)
        
#         # Filter by symbol if specified
#         symbol = self.request.query_params.get('symbol')
#         if symbol:
#             queryset = queryset.filter(symbol__icontains=symbol)
        
#         # Filter by status if specified
#         trade_status = self.request.query_params.get('status')
#         if trade_status:
#             queryset = queryset.filter(status=trade_status)
        
#         # Filter by date range
#         start_date = self.request.query_params.get('start_date')
#         end_date = self.request.query_params.get('end_date')
#         if start_date:
#             queryset = queryset.filter(open_time__date__gte=start_date)
#         if end_date:
#             queryset = queryset.filter(open_time__date__lte=end_date)
        
#         return queryset.order_by('-open_time')
    
#     @action(detail=False, methods=['get'])
#     def statistics(self, request):
#         """Get trading statistics"""
#         queryset = self.get_queryset()
        
#         # Basic stats
#         total_trades = queryset.count()
#         winning_trades = queryset.filter(profit__gt=0).count()
#         losing_trades = queryset.filter(profit__lt=0).count()
        
#         # P&L stats
#         total_profit = sum(trade.profit for trade in queryset)
#         gross_profit = sum(trade.profit for trade in queryset if trade.profit > 0)
#         gross_loss = sum(trade.profit for trade in queryset if trade.profit < 0)
        
#         # Other metrics
#         avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
#         avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0
#         win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
#         profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')
        
#         return Response({
#             'total_trades': total_trades,
#             'winning_trades': winning_trades,
#             'losing_trades': losing_trades,
#             'win_rate': round(win_rate, 2),
#             'total_profit': total_profit,
#             'gross_profit': gross_profit,
#             'gross_loss': gross_loss,
#             'average_win': round(avg_win, 2),
#             'average_loss': round(avg_loss, 2),
#             'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'Infinite',
#             'largest_win': max((trade.profit for trade in queryset), default=0),
#             'largest_loss': min((trade.profit for trade in queryset), default=0),
#         })


# class AccountActivityViewSet(viewsets.ReadOnlyModelViewSet):
#     """ViewSet for viewing account activities"""
#     serializer_class = AccountActivitySerializer
#     permission_classes = [IsAuthenticated]
#     pagination_class = StandardResultsSetPagination
    
#     def get_queryset(self):
#         queryset = AccountActivity.objects.select_related('account', 'account__user', 'related_trade')
        
#         if not self.request.user.is_staff:
#             queryset = queryset.filter(account__user=self.request.user)
        
#         # Filter by account if specified
#         account_id = self.request.query_params.get('account_id')
#         if account_id:
#             queryset = queryset.filter(account_id=account_id)
        
#         # Filter by activity type if specified
#         activity_type = self.request.query_params.get('activity_type')
#         if activity_type:
#             queryset = queryset.filter(activity_type=activity_type)
        
#         return queryset.order_by('-timestamp')


# class DashboardAPIView(APIView, MetaAPIServiceMixin):
#     """Dashboard overview API"""
#     permission_classes = [IsAuthenticated]
    
#     def get(self, request):
#         """Get dashboard data for current user"""
#         user = request.user
#         account =  get_selected_account(user)
#         # Get real-time data for all accounts
#         try:
#             response_data, response_status = self.sync_metaapi_request(
#                 'GET', f'/accounts/{account.metaapi_account_id}/equity'
#             )
#             if response_status == 200 and response_data.get('success'):
#                 real_time_data[account.id] = response_data
#         except Exception as e:
#             logger.error(f"Error fetching real-time data for account {account.id}: {e}")
        
#         # Calculate aggregated stats
#         total_balance = sum(account.balance for account in accounts)
#         total_equity = sum(account.equity for account in accounts)
#         active_accounts = accounts.filter(status='active').count()
        
#         # Get recent trades
#         recent_trades = Trade.objects.filter(
#             account__user=user
#         ).select_related('account').order_by('-open_time')[:10]
        
#         # Get recent activities
#         recent_activities = AccountActivity.objects.filter(
#             account__user=user
#         ).select_related('account').order_by('-timestamp')[:10]
        
#         # Get user profile
#         profile, _ = UserProfile.objects.get_or_create(user=user)
        
#         return Response({
#             'user_profile': UserProfileSerializer(profile).data,
#             'accounts_summary': {
#                 'total_accounts': accounts.count(),
#                 'active_accounts': active_accounts,
#                 'challenge_accounts': accounts.filter(account_type='challenge').count(),
#                 'funded_accounts': accounts.filter(account_type='funded').count(),
#                 'total_balance': total_balance,
#                 'total_equity': total_equity,
#             },
#             'accounts': TradingAccountSerializer(accounts, many=True).data,
#             'real_time_data': real_time_data,
#             'recent_trades': TradeSerializer(recent_trades, many=True).data,
#             'recent_activities': AccountActivitySerializer(recent_activities, many=True).data,
#         })


# class MetaAPIServiceStatusView(APIView, MetaAPIServiceMixin):
#     """View to check MetaAPI service status"""
#     permission_classes = [IsAuthenticated]
    
#     def get(self, request):
#         """Get MetaAPI service health status"""
#         response_data, response_status = self.sync_metaapi_request('GET', '/health')
        
#         return Response({
#             'metaapi_service_status': response_status,
#             'metaapi_service_data': response_data,
#             'connection_healthy': response_status == 200,
#         })


# class AdminDashboardView(APIView, MetaAPIServiceMixin):
#     """Admin dashboard with system-wide statistics"""
#     permission_classes = [permissions.IsAdminUser]
    
#     def get(self, request):
#         """Get admin dashboard data"""
#         # Get all accounts data from MetaAPI service
#         accounts_response, accounts_status = self.sync_metaapi_request('GET', '/accounts')
        
#         # Django database stats
#         total_users = User.objects.count()
#         total_accounts = TradingAccount.objects.count()
#         active_accounts = TradingAccount.objects.filter(status='active').count()
#         challenge_accounts = TradingAccount.objects.filter(account_type='challenge').count()
#         funded_accounts = TradingAccount.objects.filter(account_type='funded').count()
        
#         # Recent activities
#         recent_activities = AccountActivity.objects.select_related(
#             'account', 'account__user'
#         ).order_by('-timestamp')[:20]
        
#         # Trading statistics
#         total_trades = Trade.objects.count()
#         trades_today = Trade.objects.filter(
#             open_time__date=timezone.now().date()
#         ).count()
        
#         return Response({
#             'system_stats': {
#                 'total_users': total_users,
#                 'total_accounts': total_accounts,
#                 'active_accounts': active_accounts,
#                 'challenge_accounts': challenge_accounts,
#                 'funded_accounts': funded_accounts,
#                 'total_trades': total_trades,
#                 'trades_today': trades_today,
#             },
#             'metaapi_service': {
#                 'status': accounts_status,
#                 'data': accounts_response if accounts_status == 200 else None,
#             },
#             'recent_activities': AccountActivitySerializer(recent_activities, many=True).data,
#         })
    





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
    

class AccountStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, login):
        user = request.user
        try:
            account = TradingAccount.objects.get(id=login, user=user)
        except TradingAccount.DoesNotExist:
            return Response({"error": "Account not found."}, status=404)

        # Closed trades
        trades = Trade.objects.filter(account=account, status='closed')
        winning_trades = trades.filter(profit__gt=0)
        losing_trades = trades.filter(profit__lt=0)

        # Open trades
        open_trades = Trade.objects.filter(account=account, status='open')
        open_trade_data = list(open_trades.values(
            'symbol', 'type', 'position_id', 'volume', 'open_price', 'current_price', 'profit', 'open_time'
        ))

        # Daily stats
        daily_stats = DailyAccountStats.objects.filter(account=account)
        days_with_trades = daily_stats.filter(trades_count__gt=0).count()
        total_days = daily_stats.count()
        min_required_days = 10

        # Risk violations
        risk_violations = AccountActivity.objects.filter(
            account=account, activity_type='risk_violation'
        ).count()

        # Totals
        total_profit = trades.aggregate(total=Sum('profit'))['total'] or 0
        gross_profit = winning_trades.aggregate(total=Sum('profit'))['total'] or 0
        gross_loss = losing_trades.aggregate(total=Sum('profit'))['total'] or 0

        # Daily Chart Dataset
        daily_chart_data = daily_stats.annotate(
            date_str=TruncDay('date')
        ).order_by('date').values('date_str', 'daily_pnl')

        # Monthly Chart Dataset
        monthly_chart_data = (
            daily_stats.annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(monthly_pnl=Sum('daily_pnl'))
            .order_by('month')
        )

        response_data = {
            "account_type": account.account_type,
            "balance": account.balance,
            "equity": account.equity,
            "profitability": account.equity - account.balance,
            "avg_winning_trade": winning_trades.aggregate(avg=Avg('profit'))['avg'] or 0,
            "avg_losing_trade": losing_trades.aggregate(avg=Avg('profit'))['avg'] or 0,
            "min_trading_days": f"{days_with_trades}/{min_required_days}",
            "consistency": round((days_with_trades / total_days) * 100, 2) if total_days else 0,
            "profit_target": account.size * account.risk_profit_target,
            "profit_made": total_profit,
            "soft_breach_limit": f"{risk_violations}/2",
            "average_win": winning_trades.aggregate(avg=Avg('profit'))['avg'] or 0,
            "average_loss": losing_trades.aggregate(avg=Avg('profit'))['avg'] or 0,
            "profit_factor": round(gross_profit / abs(gross_loss), 2) if gross_loss else '∞',
            "win_ratio": round((winning_trades.count() / trades.count()) * 100, 2) if trades.exists() else 0,
            "HWM_balance": daily_stats.aggregate(max=Max('starting_balance'))['max'] or 0,
            "HWM_equity": daily_stats.aggregate(max=Max('highest_equity'))['max'] or 0,
            "LWM_balance": daily_stats.aggregate(min=Min('starting_balance'))['min'] or 0,
            "LWM_equity": daily_stats.aggregate(min=Min('lowest_equity'))['min'] or 0,
            
            "summary": DailySummarySerializer(daily_stats.order_by('-created_at'), many=True).data,

            "open_trades": open_trade_data,
            "daily_chart_data": [
                {
                    "date": stat["date_str"].strftime('%Y-%m-%d'),
                    "pnl": float(stat["daily_pnl"])
                } for stat in daily_chart_data
            ],
            "monthly_chart_data": [
                {
                    "month": stat["month"].strftime('%Y-%m'),
                    "pnl": float(stat["monthly_pnl"])
                } for stat in monthly_chart_data
            ]
        }

        return Response(response_data)
    