# config/settings.py
import os
from dataclasses import dataclass
from typing import List

@dataclass
class BotConfig:
    """Configurações centralizadas do bot"""
    discord_token: str
    database_url: str
    ticket_category_id: int
    suporte_role_id: int
    admin_ids: List[int]
    debug_mode: bool = False
    max_image_size: int = 5 * 1024 * 1024  # 5MB
    xp_cooldown: int = 60  # segundos
    min_xp_gain: int = 5
    max_xp_gain: int = 25
    
    @classmethod
    def from_env(cls) -> 'BotConfig':
        """Carrega configurações das variáveis de ambiente"""
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip().isdigit()]
        
        return cls(
            discord_token=os.getenv("DISCORD_TOKEN"),
            database_url=os.getenv("DATABASE_URL"),
            ticket_category_id=int(os.getenv("TICKET_CATEGORY_ID", "1392719675577598072")),
            suporte_role_id=int(os.getenv("SUPORTE_ROLE_ID", "1344088570775998545")),
            admin_ids=admin_ids,
            debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true"
        )
    
    def validate(self) -> None:
        """Valida se todas as configurações necessárias estão presentes"""
        if not self.discord_token:
            raise ValueError("DISCORD_TOKEN não encontrado nas variáveis de ambiente")
        if not self.database_url:
            raise ValueError("DATABASE_URL não encontrado nas variáveis de ambiente")
        if not self.admin_ids:
            print("⚠️ Aviso: Nenhum ADMIN_ID configurado. Comandos de admin não funcionarão.")

# Configurações de embeds e cores
class EmbedColors:
    DEFAULT = 0x7289DA
    SUCCESS = 0x43B581
    WARNING = 0xFAA61A
    ERROR = 0xF04747
    INFO = 0x3498DB
    PURPLE = 0x9B59B6
    GOLD = 0xFFD700

# Configurações de níveis
class LevelConfig:
    XP_BASE = 100
    LEVEL_COLORS = [
        "#7289DA",  # 1-10
        "#43B581",  # 11-25
        "#FAA61A",  # 26-50
        "#F04747",  # 51-75
        "#593695",  # 76-100
        "#FFD700",  # 100+
    ]
    
    @staticmethod
    def get_level_color(level: int) -> str:
        """Retorna cor baseada no nível"""
        if level <= 10:
            return LevelConfig.LEVEL_COLORS[0]
        elif level <= 25:
            return LevelConfig.LEVEL_COLORS[1]
        elif level <= 50:
            return LevelConfig.LEVEL_COLORS[2]
        elif level <= 75:
            return LevelConfig.LEVEL_COLORS[3]
        elif level <= 100:
            return LevelConfig.LEVEL_COLORS[4]
        else:
            return LevelConfig.LEVEL_COLORS[5]
