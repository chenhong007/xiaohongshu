from loguru import logger

def trans_cookies(cookies_str):
    ck = {}
    if not cookies_str:
        return ck
    
    try:
        # Handle cases where input might not be a string
        if not isinstance(cookies_str, str):
            logger.error(f"Invalid cookie type: {type(cookies_str)}")
            return ck

        # Split by semicolon and process each part
        parts = cookies_str.split(';')
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Split by the first equals sign
            if '=' in part:
                key, value = part.split('=', 1)
                ck[key.strip()] = value.strip()
            else:
                # Log warning for parts without equals sign (ignoring empty parts handled above)
                logger.warning(f"Skipping malformed cookie part (no equals sign): {part}")
                
    except Exception as e:
        logger.error(f"Error parsing cookies: {e}")
        
    return ck
