import MT5Manager
from trading.models import MT5User, MT5Deal, MT5Position, MT5UserLoginHistory

def save_mt5_user(user_obj:MT5Manager.MTUser):
    """
    Save or update an MT5 user into the Django database.
    :param user_obj: MT5 User object from the Manager API
    """
    user, _ = MT5User.objects.update_or_create(
        login=user_obj.Login,
        defaults=dict(
            group=getattr(user_obj, "Group", None),
            cert_serial_number=getattr(user_obj, "CertSerialNumber", 0),
            rights=getattr(user_obj, "Rights", 0),

            registration=getattr(user_obj, "Registration", None),
            last_access=getattr(user_obj, "LastAccess", None),
            last_ip=getattr(user_obj, "LastIP", None),

            first_name=getattr(user_obj, "FirstName", None),
            last_name=getattr(user_obj, "LastName", None),
            middle_name=getattr(user_obj, "MiddleName", None),
            name=getattr(user_obj, "Name", None),
            company=getattr(user_obj, "Company", None),
            account=getattr(user_obj, "Account", None),
            country=getattr(user_obj, "Country", None),
            city=getattr(user_obj, "City", None),
            state=getattr(user_obj, "State", None),
            zipcode=getattr(user_obj, "ZIPCode", None),
            address=getattr(user_obj, "Address", None),

            phone=getattr(user_obj, "Phone", None),
            email=getattr(user_obj, "EMail", None),
            phone_password=getattr(user_obj, "PhonePassword", None),

            id_document=getattr(user_obj, "ID", None),
            mqid=getattr(user_obj, "MQID", 0),
            client_id=getattr(user_obj, "ClientID", 0),
            visitor_id=getattr(user_obj, "VisitorID", 0),

            status=getattr(user_obj, "Status", None),
            comment=getattr(user_obj, "Comment", None),
            color=getattr(user_obj, "Color", 0),
            last_pass_change=getattr(user_obj, "LastPassChange", None),
            password_hash=getattr(user_obj, "PasswordHash", None),
            otp_secret=getattr(user_obj, "OTPSecret", None),
            leverage=getattr(user_obj, "Leverage", 100),
            language=getattr(user_obj, "Language", 0),

            lead_source=getattr(user_obj, "LeadSource", None),
            lead_campaign=getattr(user_obj, "LeadCampaign", None),

            interest_rate=getattr(user_obj, "InterestRate", 0.0),
            commission_daily=getattr(user_obj, "CommissionDaily", 0.0),
            commission_monthly=getattr(user_obj, "CommissionMonthly", 0.0),
            commission_agent_daily=getattr(user_obj, "CommissionAgentDaily", 0.0),
            commission_agent_monthly=getattr(user_obj, "CommissionAgentMonthly", 0.0),
            agent=getattr(user_obj, "Agent", 0),

            balance=getattr(user_obj, "Balance", 0.0),
            balance_prev_day=getattr(user_obj, "BalancePrevDay", 0.0),
            balance_prev_month=getattr(user_obj, "BalancePrevMonth", 0.0),
            equity_prev_day=getattr(user_obj, "EquityPrevDay", 0.0),
            equity_prev_month=getattr(user_obj, "EquityPrevMonth", 0.0),
            credit=getattr(user_obj, "Credit", 0.0),

            limit_orders=getattr(user_obj, "LimitOrders", 0),
            limit_positions_value=getattr(user_obj, "LimitPositionsValue", 0.0),
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