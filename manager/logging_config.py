import logging
import logging.handlers
from pathlib import Path

def get_prop_logger(name='prop_trading'):
    """Get a configured logger for prop trading system"""
    
    # Create logs directory if it doesn't exist
    logs_dir = Path(__file__).parent / 'logs'
    logs_dir.mkdir(exist_ok=True)
    
    # Check if logger already configured
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir / 'prop_trading.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '%(levelname)s %(asctime)s %(name)s %(funcName)s:%(lineno)d %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(logging.Formatter('%(levelname)s %(asctime)s %(message)s'))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    
    return logger