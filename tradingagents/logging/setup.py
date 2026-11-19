import logging
import os
from pathlib import Path

# === ANSI 颜色代码定义 ===
COLORS = {
    'DEBUG': '\033[36m',     # 青色
    'INFO': '\033[32m',      # 绿色
    'WARNING': '\033[33m',   # 黄色
    'ERROR': '\033[31m',     # 红色
    'CRITICAL': '\033[1;31m' # 粗体红
}
RESET = '\033[0m'
GRAY = '\033[90m'


class ColorFormatter(logging.Formatter):
    """控制台专用的彩色格式化器"""
    def format(self, record):
        # 临时保存原属性，避免影响文件日志的输出（文件里不能有颜色代码）
        original_levelname = record.levelname
        original_name = record.name
        
        # 给级别和模块名上色
        color = COLORS.get(record.levelname, '')
        if color:
            record.levelname = f"{color}{record.levelname}{RESET}"
            # 给模块名加上暗灰色，减少视觉干扰
            record.name = f"{GRAY}{record.name}{RESET}"
            
        result = super().format(record)
        
        # 恢复属性
        record.levelname = original_levelname
        record.name = original_name
        return result


def setup_logging(run_dir: Path, level: str = "INFO"):
    # 核心黑科技：强制开启 Windows 终端的 ANSI 颜色支持
    if os.name == 'nt':
        os.system('')

    logger = logging.getLogger("tradingagents")
    logger.setLevel(level)
    
    # 防止多次调用导致重复打印
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. 控制台输出（彩色，只显示级别和信息，模块名暗色）
    ch = logging.StreamHandler()
    ch.setFormatter(ColorFormatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(ch)

    # 2. 文件输出（纯文本，带时间戳，方便排查）
    run_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(fh)
    
    return logger