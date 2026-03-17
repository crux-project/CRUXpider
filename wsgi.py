"""
生产环境WSGI应用
"""
import os
import sys
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import app

# 生产环境配置
if __name__ != '__main__':
    # 禁用调试模式
    app.config['DEBUG'] = False
    
    # 设置日志配置
    import logging
    from logging.handlers import RotatingFileHandler
    
    if not app.debug:
        file_handler = RotatingFileHandler('logs/cruxpider.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('CRUXpider startup')

if __name__ == '__main__':
    # 开发环境
    from config import HOST, PORT

    app.run(host=HOST, port=PORT, debug=True)
