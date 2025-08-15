from django.contrib import admin
from .models import *

admin.site.register(Payment)
admin.site.register(Transaction)

admin.site.register(PropFirmWallet)
admin.site.register(PropFirmWalletTransaction)
# Register your models here.
