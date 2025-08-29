import MT5Manager
from trading.models import MT5User, MT5Deal, MT5Position, MT5UserLoginHistory
from datetime import datetime

def save_mt5_user(user_obj: MT5Manager.MTUser):
    """
    Save or update an MT5 user into the Django database.
    :param user_obj: MT5 User object from the Manager API
    """
    # Defensive conversion helpers
    def to_str(value):
        return str(value) if value is not None else None

    def to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def to_datetime(value):
        # MT5 returns Python datetime sometimes, but sometimes timestamp/int
        from datetime import datetime
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    user, _ = MT5User.objects.update_or_create(
        login=to_int(getattr(user_obj, "Login", 0)),
        defaults=dict(
            group=to_str(getattr(user_obj, "Group", None)),
            cert_serial_number=to_int(getattr(user_obj, "CertSerialNumber", 0)),
            rights=to_int(getattr(user_obj, "Rights", 0)),

            registration=to_datetime(getattr(user_obj, "Registration", None)),
            last_access=to_datetime(getattr(user_obj, "LastAccess", None)),
            last_ip=to_str(getattr(user_obj, "LastIP", None)),

            first_name=to_str(getattr(user_obj, "FirstName", None)),
            last_name=to_str(getattr(user_obj, "LastName", None)),
            middle_name=to_str(getattr(user_obj, "MiddleName", None)),
            name=to_str(getattr(user_obj, "Name", None)),
            company=to_str(getattr(user_obj, "Company", None)),
            account=to_str(getattr(user_obj, "Account", None)),
            country=to_str(getattr(user_obj, "Country", None)),
            city=to_str(getattr(user_obj, "City", None)),
            state=to_str(getattr(user_obj, "State", None)),
            zipcode=to_str(getattr(user_obj, "ZIPCode", None)),
            address=to_str(getattr(user_obj, "Address", None)),

            phone=to_str(getattr(user_obj, "Phone", None)),
            email=to_str(getattr(user_obj, "EMail", None)),
            phone_password=to_str(getattr(user_obj, "PhonePassword", None)),

            id_document=to_str(getattr(user_obj, "ID", None)),
            mqid=to_int(getattr(user_obj, "MQID", 0)),
            client_id=to_int(getattr(user_obj, "ClientID", 0)),
            visitor_id=to_int(getattr(user_obj, "VisitorID", 0)),

            status=to_str(getattr(user_obj, "Status", None)),
            comment=to_str(getattr(user_obj, "Comment", None)),
            color=to_int(getattr(user_obj, "Color", 0)),
            last_pass_change=to_datetime(getattr(user_obj, "LastPassChange", None)),
            password_hash=to_str(getattr(user_obj, "PasswordHash", None)),
            otp_secret=to_str(getattr(user_obj, "OTPSecret", None)),
            leverage=to_int(getattr(user_obj, "Leverage", 100)),
            language=to_int(getattr(user_obj, "Language", 0)),

            lead_source=to_str(getattr(user_obj, "LeadSource", None)),
            lead_campaign=to_str(getattr(user_obj, "LeadCampaign", None)),

            interest_rate=to_float(getattr(user_obj, "InterestRate", 0.0)),
            commission_daily=to_float(getattr(user_obj, "CommissionDaily", 0.0)),
            commission_monthly=to_float(getattr(user_obj, "CommissionMonthly", 0.0)),
            commission_agent_daily=to_float(getattr(user_obj, "CommissionAgentDaily", 0.0)),
            commission_agent_monthly=to_float(getattr(user_obj, "CommissionAgentMonthly", 0.0)),
            agent=to_int(getattr(user_obj, "Agent", 0)),

            balance=to_float(getattr(user_obj, "Balance", 0.0)),
            balance_prev_day=to_float(getattr(user_obj, "BalancePrevDay", 0.0)),
            balance_prev_month=to_float(getattr(user_obj, "BalancePrevMonth", 0.0)),
            equity_prev_day=to_float(getattr(user_obj, "EquityPrevDay", 0.0)),
            equity_prev_month=to_float(getattr(user_obj, "EquityPrevMonth", 0.0)),
            credit=to_float(getattr(user_obj, "Credit", 0.0)),

            limit_orders=to_int(getattr(user_obj, "LimitOrders", 0)),
            limit_positions_value=to_float(getattr(user_obj, "LimitPositionsValue", 0.0)),
        )
    )
    return user




def delete_user(login):
    MT5User.objects.filter(login=login).delete()
    MT5Position.objects.filter(login=login).delete()
    MT5Deal.objects.filter(login=login).delete()


class UserSink: 
    def OnUserDelete(self, user:MT5Manager.MTUser) -> None: 
        print(f"User with login: {user.Login} was deleted")
    
    def OnUserAdd(self, user:MT5Manager.MTUser):
        print("User added", user.Login)
        save_mt5_user(user)

    def OnUserAdd(self, user:MT5Manager.MTUser):
        print("User updated", user.Login)
        save_mt5_user(user)

    def OnUserDelete(self, user:MT5Manager.MTUser):
        print("User deleted", user.Login)
        delete_user()

    def OnUserClean(self, login):
        print("User deleted", login)
        delete_user()

    def OnUserLogin(ip:str, user:MT5Manager.MTUser, type):
        try:
            mt_user = MT5User.objects.get(login=user.Login)
            MT5UserLoginHistory.objects.create(mt_user=mt_user, action='login', ip=ip, type=type)
        except Exception as err:
            pass

    def OnUserLogout(ip:str, user:MT5Manager.MTUser, type):
        try:
            mt_user = MT5User.objects.get(login=user.Login)
            MT5UserLoginHistory.objects.create(mt_user=mt_user, action='logout', ip=ip, type=type)
        except Exception as err:
            pass