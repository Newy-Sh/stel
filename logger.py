import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

def setup_logger(
    name: str = "stellaris_bot",
    log_level: int = logging.INFO,
    log_file: Optional[str] = "logs/bot.log",
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Configura e retorna um logger personalizado para o bot
    
    Args:
        name: Nome do logger
        log_level: Nível de logging
        log_file: Caminho para o arquivo de log (None para desabilitar)
        max_file_size: Tamanho máximo do arquivo em bytes
        backup_count: Número de backups a manter
    """
    
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Limpar handlers existentes
    logger.handlers.clear()
    
    # Formato das mensagens
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler para arquivo (se especificado)
    if log_file:
        # Criar diretório se não existir
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        from logging.handlers import RotatingFileHandler
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

class BotLogger:
    """Classe para logging específico do bot com métodos convenientes"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def command_used(self, user: str, guild: str, command: str, **kwargs):
        """Log de uso de comando"""
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.info(f"COMMAND | {user} in {guild} used /{command}" + 
                        (f" | {extra_info}" if extra_info else ""))
    
    def error_occurred(self, error: Exception, context: str = "", **kwargs):
        """Log de erro com contexto"""
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.error(f"ERROR | {context} | {type(error).__name__}: {error}" +
                         (f" | {extra_info}" if extra_info else ""))
    
    def user_action(self, user: str, action: str, target: str = "", **kwargs):
        """Log de ação do usuário"""
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        target_info = f" -> {target}" if target else ""
        self.logger.info(f"ACTION | {user} {action}{target_info}" +
                        (f" | {extra_info}" if extra_info else ""))
    
    def database_operation(self, operation: str, table: str, **kwargs):
        """Log de operação no banco de dados"""
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.debug(f"DB | {operation} on {table}" +
                         (f" | {extra_info}" if extra_info else ""))
    
    def security_event(self, event_type: str, user: str, details: str = "", **kwargs):
        """Log de evento de segurança"""
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.warning(f"SECURITY | {event_type} | {user} | {details}" +
                           (f" | {extra_info}" if extra_info else ""))
    
    def performance_metric(self, metric: str, value: float, unit: str = "", **kwargs):
        """Log de métricas de performance"""
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.info(f"PERF | {metric}: {value}{unit}" +
                        (f" | {extra_info}" if extra_info else ""))

# Instância global do logger
bot_logger = None

def get_logger() -> BotLogger:
    """Retorna a instância global do logger"""
    global bot_logger
    if bot_logger is None:
        logger = setup_logger()
        bot_logger = BotLogger(logger)
    return bot_logger

def init_logging(debug_mode: bool = False) -> BotLogger:
    """Inicializa o sistema de logging"""
    global bot_logger
    
    log_level = logging.DEBUG if debug_mode else logging.INFO
    logger = setup_logger(log_level=log_level)
    bot_logger = BotLogger(logger)
    
    # Log inicial
    logger.info("=" * 50)
    logger.info("🚀 Stellaris Bot - Sistema de Logging Inicializado")
    logger.info(f"📊 Nível de Log: {logging.getLevelName(log_level)}")
    logger.info(f"🕒 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)
    
    return bot_logger
