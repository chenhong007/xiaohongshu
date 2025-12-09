import browser_cookie3
from loguru import logger

def trans_cookies(cookies_str):
    if '; ' in cookies_str:
        ck = {i.split('=')[0]: '='.join(i.split('=')[1:]) for i in cookies_str.split('; ')}
    else:
        ck = {i.split('=')[0]: '='.join(i.split('=')[1:]) for i in cookies_str.split(';')}
    return ck

def get_cookie_from_browser(browser_name):
    """
    从浏览器获取 cookie
    :param browser_name: 浏览器名称，支持 Chrome, Edge, Firefox
    :return: cookie 字典
    """
    try:
        if browser_name.lower() == 'chrome':
            cj = browser_cookie3.chrome(domain_name='.xiaohongshu.com')
        elif browser_name.lower() == 'edge':
            cj = browser_cookie3.edge(domain_name='.xiaohongshu.com')
        elif browser_name.lower() == 'firefox':
            cj = browser_cookie3.firefox(domain_name='.xiaohongshu.com')
        else:
            logger.error(f"不支持的浏览器: {browser_name}")
            return None
        
        cookie_dict = {}
        for cookie in cj:
            cookie_dict[cookie.name] = cookie.value
        
        # 转换为字符串格式，以便兼容现有代码
        cookie_str = '; '.join([f'{k}={v}' for k, v in cookie_dict.items()])
        return cookie_str
    except Exception as e:
        error_msg = str(e)
        if "admin" in error_msg.lower():
            logger.error(f"从 {browser_name} 获取 Cookie 失败: 需要管理员权限。请尝试以管理员身份运行终端/命令行，或手动提取 Cookie。")
        else:
            logger.error(f"从 {browser_name} 获取 Cookie 失败: {e}")
        return None
