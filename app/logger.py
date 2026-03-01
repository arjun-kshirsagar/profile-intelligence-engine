import logging
import sys
from typing import Optional

def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Sets up logging for the application."""
    logger = logging.getLogger("profile_engine")
    
    if not logger.handlers:
        logger.setLevel(level)
        
        # Create console handler with a higher log level
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        
        # Create formatter and add it to the handlers
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        ch.setFormatter(formatter)
        
        # Add the handlers to the logger
        logger.addHandler(ch)
        
    return logger

# Create a default logger instance
logger = setup_logging()
