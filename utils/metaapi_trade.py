from metaapi_cloud_sdk import MetaApi
from django.conf import settings
import requests

def place_buy_order_via_worker(account_id, symbol, volume, type: str, stop_loss=None, take_profit=None, open_price=None,):
    url = 'http://127.0.0.1:8001/create_buy_order'
    data = {
        "account_id": account_id,
        "symbol": symbol,
        "volume": volume,
        "type": type,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "open_price": open_price
    }
    resp = requests.post(url, json=data)
    resp_json = resp.json()
    print(resp_json)
    return resp_json['success'], resp_json['message']


def place_sell_order_via_worker(account_id, symbol, volume, type: str, stop_loss=None, take_profit=None, open_price=None,):
    url = 'http://127.0.0.1:8001/create_sell_order'
    data = {
        "account_id": account_id,
        "symbol": symbol,
        "volume": volume,
        "type": type,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "open_price": open_price
    }
    resp = requests.post(url, json=data)
    resp_json = resp.json()
    print(resp_json)
    return resp_json['success'], resp_json['message']


def close_position_via_worker(account_id, position_id):
    url = 'http://127.0.0.1:8001/close_position'
    data = {
        "account_id": account_id,
        "position_id": position_id,
    }
    resp = requests.post(url, json=data)
    resp_json = resp.json()
    print(resp_json)
    return resp_json['success'], resp_json['message']


def modify_position_via_worker(account_id, position_id, stop_loss, take_profit):
    url = 'http://127.0.0.1:8001/modify_position'
    data = {
        "account_id": account_id,
        "position_id": position_id,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }
    resp = requests.post(url, json=data)
    resp_json = resp.json()
    print(resp_json)
    return resp_json['success'], resp_json['message']


def modify_order_via_worker(account_id, order_id, open_price, stop_loss, take_profit):
    url = 'http://127.0.0.1:8001/modify_order'
    data = {
        "account_id": account_id,
        "order_id": order_id,
        "open_price": open_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }
    resp = requests.post(url, json=data)
    resp_json = resp.json()
    print(resp_json)
    return resp_json['success'], resp_json['message']



def cancel_order_via_worker(account_id, order_id):
    url = 'http://127.0.0.1:8001/cancel_order'
    data = {
        "account_id": account_id,
        "order_id": order_id,
    }
    resp = requests.post(url, json=data)
    resp_json = resp.json()
    print(resp_json)
    return resp_json['success'], resp_json['message']



async def create_market_sell_order(account_id: str, symbol: str, volume, stop_loss, take_profit):
    metaapi = MetaApi(settings.METAAPI_TOKEN)
    account = await metaapi.metatrader_account_api.get_account(account_id)
    
    connection = account.get_rpc_connection()

    try:
        await connection.connect()
        await connection.wait_synchronized()  # Wait for account state to sync
        
        sell = await connection.create_market_sell_order(
            symbol=symbol, volume=volume, stop_loss=stop_loss, take_profit=take_profit,
            options={'comment': 'comment', 'clientId': 'TE_GBPUSD_7hyINWqAl'}
        )
    except Exception as e:
        # Log or handle errors here
        print(f"Failed to place order: {str(e)}")
        return False, str(e)
    
    return True, sell


async def create_stop_buy_order(account_id: str, symbol: str, volume, open_price, stop_loss, take_profit):
    metaapi = MetaApi(settings.METAAPI_TOKEN)
    account = await metaapi.metatrader_account_api.get_account(account_id)
    
    connection = account.get_rpc_connection()

    try:
        await connection.connect()
        await connection.wait_synchronized()  # Wait for account state to sync
        
        buy = await connection.create_stop_buy_order(
            symbol=symbol, volume=volume, open_price=open_price, stop_loss=stop_loss,take_profit=take_profit, 
            options={'comment': 'comment', 'clientId': 'TE_GBPUSD_7hyINWqAl'}
        )
    except Exception as e:
        # Log or handle errors here
        print(f"Failed to place order: {str(e)}")
        return False, str(e)
    
    return True, buy


async def create_stop_sell_order(account_id: str, symbol: str, volume, open_price, stop_loss, take_profit):
    metaapi = MetaApi(settings.METAAPI_TOKEN)
    account = await metaapi.metatrader_account_api.get_account(account_id)
    
    connection = account.get_rpc_connection()

    try:
        await connection.connect()
        await connection.wait_synchronized()  # Wait for account state to sync
        
        sell = await connection.create_stop_sell_order(
            symbol=symbol, volume=volume, open_price=open_price, stop_loss=stop_loss,take_profit=take_profit, 
            options={'comment': 'comment', 'clientId': 'TE_GBPUSD_7hyINWqAl'}
        )
    except Exception as e:
        # Log or handle errors here
        print(f"Failed to place order: {str(e)}")
        return False, str(e)
    
    return True, sell


async def create_limit_buy_order(account_id: str, symbol: str, volume, open_price, stop_loss, take_profit):
    metaapi = MetaApi(settings.METAAPI_TOKEN)
    account = await metaapi.metatrader_account_api.get_account(account_id)
    
    connection = account.get_rpc_connection()

    try:
        await connection.connect()
        await connection.wait_synchronized()  # Wait for account state to sync
        
        buy = await connection.create_limit_buy_order(
            symbol=symbol, volume=volume, open_price=open_price, stop_loss=stop_loss,take_profit=take_profit, 
            options={'comment': 'comment', 'clientId': 'TE_GBPUSD_7hyINWqAl'}
        )
    except Exception as e:
        # Log or handle errors here
        print(f"Failed to place order: {str(e)}")
        return False, str(e)
    
    return True, buy



async def create_limit_sell_order(account_id: str, symbol: str, volume, open_price, stop_loss, take_profit):
    metaapi = MetaApi(settings.METAAPI_TOKEN)
    account = await metaapi.metatrader_account_api.get_account(account_id)
    
    connection = account.get_rpc_connection()

    try:
        await connection.connect()
        await connection.wait_synchronized()  # Wait for account state to sync
        
        sell = await connection.create_limit_sell_order(
            symbol=symbol, volume=volume, open_price=open_price, stop_loss=stop_loss,take_profit=take_profit, 
            options={'comment': 'comment', 'clientId': 'TE_GBPUSD_7hyINWqAl'}
        )
    except Exception as e:
        # Log or handle errors here
        print(f"Failed to place order: {str(e)}")
        return False, str(e)
    
    return True, sell