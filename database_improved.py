# database_improved.py
import asyncpg
import os
from datetime import datetime, timedelta
import asyncio
from typing import Optional, Dict, List
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import get_logger

class Database:
    def __init__(self):
        self.pool = None
        self.logger = get_logger()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def connect(self):
        """Conecta ao banco de dados PostgreSQL com retry automático"""
        try:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise ValueError("DATABASE_URL não encontrado nas variáveis de ambiente")
            
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=5,
                max_size=20,
                command_timeout=60,
                server_settings={
                    'jit': 'off'  # Desabilita JIT para melhor performance em queries pequenas
                }
            )
            await self.create_tables()
            self.logger.logger.info("✅ Conectado ao banco de dados PostgreSQL")
            
        except Exception as e:
            self.logger.error_occurred(e, "Conexão com banco de dados")
            raise
    
    async def close(self):
        """Fecha o pool de conexões"""
        if self.pool:
            await self.pool.close()
            self.logger.logger.info("🔌 Conexão com banco de dados fechada")
    
    async def create_tables(self):
        """Cria as tabelas necessárias com otimizações"""
        async with self.pool.acquire() as conn:
            # Tabela de usuários
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT NOT NULL,
                    guild_id BIGINT NOT NULL,
                    xp BIGINT DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    messages_sent INTEGER DEFAULT 0,
                    banner_url TEXT DEFAULT NULL,
                    bio TEXT DEFAULT NULL,
                    favorite_color TEXT DEFAULT '#7289DA',
                    last_xp_gain TIMESTAMP DEFAULT NOW(),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            
            # Índices otimizados
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_guild_xp 
                ON users (guild_id, xp DESC)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_level 
                ON users (guild_id, level DESC)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_last_xp_gain 
                ON users (user_id, guild_id, last_xp_gain)
            """)
            
            # Tabela de estatísticas do servidor (nova)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_stats (
                    guild_id BIGINT PRIMARY KEY,
                    total_messages BIGINT DEFAULT 0,
                    total_xp_given BIGINT DEFAULT 0,
                    active_users_today INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Tabela de backup de dados (nova)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS data_backups (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT,
                    backup_type VARCHAR(50),
                    backup_data JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Trigger para atualizar updated_at automaticamente
            await conn.execute("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
            """)
            
            await conn.execute("""
                DROP TRIGGER IF EXISTS update_users_updated_at ON users;
                CREATE TRIGGER update_users_updated_at 
                    BEFORE UPDATE ON users 
                    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            """)
    
    async def get_user_data(self, user_id: int, guild_id: int) -> Dict:
        """Obtém dados de um usuário, criando se não existir"""
        async with self.pool.acquire() as conn:
            try:
                # Tenta inserir o usuário se não existir
                await conn.execute("""
                    INSERT INTO users (user_id, guild_id) 
                    VALUES ($1, $2)
                    ON CONFLICT (user_id, guild_id) DO NOTHING
                """, user_id, guild_id)
                
                # Busca os dados do usuário
                row = await conn.fetchrow("""
                    SELECT * FROM users 
                    WHERE user_id = $1 AND guild_id = $2
                """, user_id, guild_id)
                
                if row:
                    self.logger.database_operation("SELECT", "users", user_id=user_id, guild_id=guild_id)
                    return dict(row)
                
                # Fallback se algo der errado
                return {
                    'user_id': user_id,
                    'guild_id': guild_id,
                    'xp': 0,
                    'level': 1,
                    'messages_sent': 0,
                    'banner_url': None,
                    'bio': None,
                    'favorite_color': '#7289DA',
                    'last_xp_gain': datetime.now(),
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                }
                
            except Exception as e:
                self.logger.error_occurred(e, "get_user_data", user_id=user_id, guild_id=guild_id)
                raise
    
    async def add_xp(self, user_id: int, guild_id: int, xp_amount: int) -> Dict:
        """Adiciona XP ao usuário com melhor controle de concorrência"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # Garantir que o usuário existe
                    await conn.execute("""
                        INSERT INTO users (user_id, guild_id, last_xp_gain)
                        VALUES ($1, $2, NOW() - INTERVAL '2 minutes')
                        ON CONFLICT (user_id, guild_id) DO NOTHING
                    """, user_id, guild_id)
                    
                    # Buscar dados atuais com lock
                    old_data = await conn.fetchrow("""
                        SELECT xp, level, messages_sent, last_xp_gain
                        FROM users 
                        WHERE user_id = $1 AND guild_id = $2
                        FOR UPDATE
                    """, user_id, guild_id)
                    
                    if not old_data:
                        return {'levelup': False, 'new_level': 1}
                    
                    # Verificar cooldown (60 segundos)
                    now = datetime.now()
                    if old_data['last_xp_gain'] and old_data['messages_sent'] > 0:
                        time_diff = now - old_data['last_xp_gain']
                        if time_diff < timedelta(seconds=60):
                            return {
                                'levelup': False,
                                'new_level': old_data['level'],
                                'old_level': old_data['level'],
                                'new_xp': old_data['xp'],
                                'xp_gained': 0,
                                'cooldown': True
                            }
                    
                    # Atualizar dados
                    update_result = await conn.fetchrow("""
                        UPDATE users 
                        SET 
                            xp = xp + $3,
                            level = GREATEST(1, CAST(FLOOR(SQRT((xp + $3) / 100.0)) + 1 AS INTEGER)),
                            messages_sent = messages_sent + 1,
                            last_xp_gain = NOW()
                        WHERE user_id = $1 AND guild_id = $2
                        RETURNING xp, level
                    """, user_id, guild_id, xp_amount)
                    
                    if not update_result:
                        return {'levelup': False, 'new_level': old_data['level']}
                    
                    # Atualizar estatísticas do servidor
                    await conn.execute("""
                        INSERT INTO guild_stats (guild_id, total_messages, total_xp_given)
                        VALUES ($1, 1, $2)
                        ON CONFLICT (guild_id) 
                        DO UPDATE SET 
                            total_messages = guild_stats.total_messages + 1,
                            total_xp_given = guild_stats.total_xp_given + $2,
                            last_updated = NOW()
                    """, guild_id, xp_amount)
                    
                    old_level = old_data['level']
                    new_level = update_result['level']
                    levelup = new_level > old_level
                    
                    result = {
                        'levelup': levelup,
                        'new_level': new_level,
                        'old_level': old_level,
                        'new_xp': update_result['xp'],
                        'xp_gained': xp_amount,
                        'cooldown': False
                    }
                    
                    if levelup:
                        self.logger.user_action(
                            f"User#{user_id}", 
                            "LEVEL_UP", 
                            f"Level {old_level} -> {new_level}",
                            guild_id=guild_id
                        )
                    
                    return result
                    
                except Exception as e:
                    self.logger.error_occurred(e, "add_xp", user_id=user_id, guild_id=guild_id)
                    raise
    
    async def get_leaderboard(self, guild_id: int, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Obtém o ranking do servidor com paginação"""
        async with self.pool.acquire() as conn:
            try:
                rows = await conn.fetch("""
                    SELECT user_id, xp, level, messages_sent
                    FROM users 
                    WHERE guild_id = $1 
                    ORDER BY xp DESC 
                    LIMIT $2 OFFSET $3
                """, guild_id, limit, offset)
                
                self.logger.database_operation("SELECT_LEADERBOARD", "users", guild_id=guild_id, limit=limit)
                return [dict(row) for row in rows]
                
            except Exception as e:
                self.logger.error_occurred(e, "get_leaderboard", guild_id=guild_id)
                raise
    
    async def get_user_rank(self, user_id: int, guild_id: int) -> int:
        """Obtém a posição do usuário no ranking (otimizado)"""
        async with self.pool.acquire() as conn:
            try:
                # Garantir que o usuário existe
                await self.get_user_data(user_id, guild_id)
                
                rank = await conn.fetchval("""
                    SELECT COUNT(*) + 1
                    FROM users 
                    WHERE guild_id = $1 AND xp > COALESCE((
                        SELECT xp FROM users 
                        WHERE user_id = $2 AND guild_id = $1
                    ), 0)
                """, guild_id, user_id)
                
                return rank or 1
                
            except Exception as e:
                self.logger.error_occurred(e, "get_user_rank", user_id=user_id, guild_id=guild_id)
                return 1
    
    async def get_server_stats(self, guild_id: int) -> Dict:
        """Obtém estatísticas gerais do servidor"""
        async with self.pool.acquire() as conn:
            try:
                user_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_users,
                        COALESCE(AVG(level), 1) as avg_level,
                        COALESCE(MAX(level), 1) as max_level,
                        COALESCE(SUM(messages_sent), 0) as total_messages,
                        COALESCE(SUM(xp), 0) as total_xp
                    FROM users 
                    WHERE guild_id = $1
                """, guild_id)
                
                guild_stats = await conn.fetchrow("""
                    SELECT * FROM guild_stats WHERE guild_id = $1
                """, guild_id)
                
                result = dict(user_stats) if user_stats else {}
                if guild_stats:
                    result.update(dict(guild_stats))
                
                return result
                
            except Exception as e:
                self.logger.error_occurred(e, "get_server_stats", guild_id=guild_id)
                return {}
    
    async def update_banner(self, user_id: int, guild_id: int, banner_url: str):
        """Atualiza o banner do usuário"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE users 
                    SET banner_url = $3 
                    WHERE user_id = $1 AND guild_id = $2
                """, user_id, guild_id, banner_url)
                
                self.logger.user_action(f"User#{user_id}", "UPDATE_BANNER", banner_url[:50])
                
            except Exception as e:
                self.logger.error_occurred(e, "update_banner", user_id=user_id)
                raise
    
    async def update_bio(self, user_id: int, guild_id: int, bio: str):
        """Atualiza a bio do usuário"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE users 
                    SET bio = $3 
                    WHERE user_id = $1 AND guild_id = $2
                """, user_id, guild_id, bio)
                
                self.logger.user_action(f"User#{user_id}", "UPDATE_BIO", bio[:30])
                
            except Exception as e:
                self.logger.error_occurred(e, "update_bio", user_id=user_id)
                raise
    
    async def update_favorite_color(self, user_id: int, guild_id: int, color: str):
        """Atualiza a cor favorita do usuário"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE users 
                    SET favorite_color = $3 
                    WHERE user_id = $1 AND guild_id = $2
                """, user_id, guild_id, color)
                
                self.logger.user_action(f"User#{user_id}", "UPDATE_COLOR", color)
                
            except Exception as e:
                self.logger.error_occurred(e, "update_favorite_color", user_id=user_id)
                raise
    
    # Métodos de utilidade existentes mantidos
    def calculate_level(self, xp: int) -> int:
        """Calcula o nível baseado no XP"""
        import math
        if xp < 100:
            return 1
        return int(math.sqrt(xp / 100)) + 1
    
    def xp_needed_for_next_level(self, level: int) -> int:
        """Calcula quanto XP é necessário para o próximo nível"""
        return ((level ** 2) * 100) - (((level - 1) ** 2) * 100)
    
    def xp_for_level(self, level: int) -> int:
        """Calcula o XP total necessário para um nível"""
        return ((level - 1) ** 2) * 100
    
    async def create_backup(self, guild_id: int, backup_type: str = "manual") -> bool:
        """Cria backup dos dados do servidor"""
        async with self.pool.acquire() as conn:
            try:
                # Buscar todos os dados dos usuários
                users_data = await conn.fetch("""
                    SELECT * FROM users WHERE guild_id = $1
                """, guild_id)
                
                # Buscar estatísticas do servidor
                guild_stats = await conn.fetchrow("""
                    SELECT * FROM guild_stats WHERE guild_id = $1
                """, guild_id)
                
                backup_data = {
                    "users": [dict(row) for row in users_data],
                    "guild_stats": dict(guild_stats) if guild_stats else None,
                    "timestamp": datetime.now().isoformat(),
                    "total_users": len(users_data)
                }
                
                # Salvar backup
                await conn.execute("""
                    INSERT INTO data_backups (guild_id, backup_type, backup_data)
                    VALUES ($1, $2, $3)
                """, guild_id, backup_type, backup_data)
                
                self.logger.logger.info(f"📦 Backup criado para guild {guild_id}: {len(users_data)} usuários")
                return True
                
            except Exception as e:
                self.logger.error_occurred(e, "create_backup", guild_id=guild_id)
                return False

# Instância global
db = Database()