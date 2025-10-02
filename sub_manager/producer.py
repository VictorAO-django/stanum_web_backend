import redis
from django.conf import settings
from confluent_kafka import Producer
from channels.layers import get_channel_layer

p = Producer({"bootstrap.servers": "localhost:9092"})

# Create connection pool
redis_pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=50
)

# Create client from pool
redis_client = redis.Redis(connection_pool=redis_pool)

channel_layer = get_channel_layer()