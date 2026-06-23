import discord
from typing import Optional, List, Dict, Any
from config.settings import EmbedColors

class EmbedBuilder:
    """Construtor de embeds padronizados"""
    
    @staticmethod
    def success(title: str, description: str = None, **kwargs) -> discord.Embed:
        """Cria embed de sucesso"""
        embed = discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=EmbedColors.SUCCESS,
            **kwargs
        )
        return embed
    
    @staticmethod
    def error(title: str, description: str = None, **kwargs) -> discord.Embed:
        """Cria embed de erro"""
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=EmbedColors.ERROR,
            **kwargs
        )
        return embed
    
    @staticmethod
    def warning(title: str, description: str = None, **kwargs) -> discord.Embed:
        """Cria embed de aviso"""
        embed = discord.Embed(
            title=f"⚠️ {title}",
            description=description,
            color=EmbedColors.WARNING,
            **kwargs
        )
        return embed
    
    @staticmethod
    def info(title: str, description: str = None, **kwargs) -> discord.Embed:
        """Cria embed informativo"""
        embed = discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=EmbedColors.INFO,
            **kwargs
        )
        return embed
    
    @staticmethod
    def level_up(user: discord.Member, old_level: int, new_level: int, xp_gained: int) -> discord.Embed:
        """Cria embed de level up"""
        embed = discord.Embed(
            title="🎉 Level Up!",
            description=f"Parabéns {user.mention}! Você subiu para o **Nível {new_level}**!",
            color=EmbedColors.GOLD
        )
        embed.add_field(name="XP Ganho", value=f"+{xp_gained} XP", inline=True)
        embed.add_field(name="Nível Anterior", value=str(old_level), inline=True)
        embed.add_field(name="Novo Nível", value=str(new_level), inline=True)
        return embed
    
    @staticmethod
    def profile(user: discord.Member, user_data: Dict, rank: int) -> discord.Embed:
        """Cria embed de perfil"""
        current_level = user_data['level']
        current_xp = user_data['xp']
        xp_for_current = ((current_level - 1) ** 2) * 100
        xp_for_next = (current_level ** 2) * 100
        xp_in_level = current_xp - xp_for_current
        xp_needed = xp_for_next - xp_for_current
        
        progress_percent = (xp_in_level / xp_needed) * 100 if xp_needed > 0 else 100
        
        embed = discord.Embed(
            title=f"📊 Nível de {user.display_name}",
            color=discord.Color.from_str(user_data.get('favorite_color', '#7289DA'))
        )
        
        embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)
        
        embed.add_field(name="🏆 Nível", value=f"**{current_level}**", inline=True)
        embed.add_field(name="📈 Ranking", value=f"**#{rank}**", inline=True)
        embed.add_field(name="💫 XP Total", value=f"{current_xp:,}", inline=True)
        
        embed.add_field(name="📊 Progresso", value=f"{xp_in_level:,} / {xp_needed:,} XP", inline=True)
        embed.add_field(name="🎯 Próximo Nível", value=f"{progress_percent:.1f}%", inline=True)
        embed.add_field(name="💬 Mensagens", value=f"{user_data['messages_sent']:,}", inline=True)
        
        # Barra de progresso
        progress_bar_length = 20
        filled = int(progress_bar_length * (progress_percent / 100))
        empty = progress_bar_length - filled
        progress_bar = "█" * filled + "░" * empty
        
        embed.add_field(name="📈 Barra de Progresso", value=f"`{progress_bar}`", inline=False)
        
        return embed
    
    @staticmethod
    def ticket_welcome(ticket_number: str, ticket_type: str, user: discord.Member) -> discord.Embed:
        """Cria embed de boas-vindas do ticket"""
        import datetime
        
        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_number} - {ticket_type}",
            description=(
                f"Olá {user.mention}! Seja Bem-vindo(a) ao seu ticket.\n\n"
                f"**📋 Número:** #{ticket_number}\n"
                f"**📂 Tipo:** {ticket_type}\n"
                f"**📅 Criado em:** {datetime.datetime.now().strftime('%d/%m/%Y às %H:%M')}\n"
                f"**👤 Solicitante:** {user.display_name}\n\n"
                "📝 Descreva detalhadamente sua solicitação abaixo e seu motivo de contatação.\n"
                "⏰ Nossa equipe responderá em breve, aguarde.\n\n"
                "Para fechar este ticket, clique no botão abaixo."
            ),
            color=EmbedColors.INFO
        )
        return embed
    
    @staticmethod
    def moderation_action(action: str, target: discord.Member, moderator: discord.Member, reason: str) -> discord.Embed:
        """Cria embed para ações de moderação"""
        colors = {
            "ban": EmbedColors.ERROR,
            "kick": EmbedColors.WARNING,
            "timeout": EmbedColors.WARNING
        }
        
        icons = {
            "ban": "🔨",
            "kick": "👢", 
            "timeout": "⏰"
        }
        
        titles = {
            "ban": "Usuário Banido",
            "kick": "Usuário Expulso",
            "timeout": "Timeout Aplicado"
        }
        
        embed = discord.Embed(
            title=f"{icons.get(action, '⚖️')} {titles.get(action, 'Ação de Moderação')}",
            description=f"**Usuário:** {target.mention} ({target})\n**Motivo:** {reason}\n**Moderador:** {moderator.mention}",
            color=colors.get(action, EmbedColors.DEFAULT),
            timestamp=discord.utils.utcnow()
        )
        return embed

class MessageFormatter:
    """Formatador de mensagens"""
    
    @staticmethod
    def sanitize_mentions(text: str) -> str:
        """Remove menções maliciosas"""
        return text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
        """Trunca texto se for muito longo"""
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix
    
    @staticmethod
    def format_number(number: int) -> str:
        """Formata números com separadores"""
        return f"{number:,}"
    
    @staticmethod
    def format_progress_bar(current: int, total: int, length: int = 20) -> str:
        """Cria barra de progresso visual"""
        if total == 0:
            return "░" * length
        
        progress = current / total
        filled = int(length * progress)
        empty = length - filled
        return "█" * filled + "░" * empty
