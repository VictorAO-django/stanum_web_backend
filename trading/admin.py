from django.contrib import admin
from .models import *

admin.site.register(TradingAccount)
admin.site.register(Trade)
admin.site.register(AccountActivity)
admin.site.register(DailyAccountStats)
admin.site.register(UserProfile)

admin.site.register(MT5User)
admin.site.register(MT5Account)
admin.site.register(MT5Daily)
admin.site.register(MT5Deal)
admin.site.register(MT5Order)
admin.site.register(MT5Position)
admin.site.register(MT5OrderHistory)
admin.site.register(MT5Summary)
admin.site.register(MT5UserLoginHistory)
# Register your models here.
