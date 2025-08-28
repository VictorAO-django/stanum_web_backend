from typing import TypedDict, Literal, Optional

class NewAccountData(TypedDict):
    first_name: str
    last_name: str
    balance: int
    country: str
    company: str
    address: str
    email: str
    phone: str
    zip_code: str
    state: str
    city: str
    language: str
    comment: str
    challenge_name: str
    bridge_secret: str