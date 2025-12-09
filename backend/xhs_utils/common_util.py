import os
from loguru import logger
from dotenv import load_dotenv

def load_env():
    # Explicitly look for .env in the backend directory
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        # Fallback to default behavior
        load_dotenv()
        
    cookies_str = os.getenv('COOKIES')
    return cookies_str

def update_env_cookies(cookies_str):
    """Update or create .env file with the new cookies string."""
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        
        # Read existing lines if file exists
        lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        
        # Update COOKIES line or append it
        cookie_found = False
        new_lines = []
        for line in lines:
            if line.strip().startswith('COOKIES='):
                new_lines.append(f'COOKIES={cookies_str}\n')
                cookie_found = True
            else:
                new_lines.append(line)
        
        if not cookie_found:
            new_lines.append(f'COOKIES={cookies_str}\n')
            
        # Write back to file
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
            
        # Reload environment variables
        os.environ['COOKIES'] = cookies_str
        logger.info(f"Successfully updated cookies in {env_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to update .env file: {e}")
        return False

def init():
    media_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/media_datas'))
    excel_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/excel_datas'))
    for base_path in [media_base_path, excel_base_path]:
        if not os.path.exists(base_path):
            os.makedirs(base_path)
            logger.info(f'创建目录 {base_path}')
    cookies_str = load_env()
    base_path = {
        'media': media_base_path,
        'excel': excel_base_path,
    }
    return cookies_str, base_path
