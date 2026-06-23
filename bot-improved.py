# bot_improved.py
import discord
from discord.ext import commands
import os
import random
import datetime
import asyncio
from dotenv import load_dotenv
import sys
from pathlib import Path
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Adicionar o diretório atual ao path para imports
sys.path.append(str(Path(__file__).parent))

from config.settings import BotConfig, EmbedColors
from utils.logger import init_logging, get_logger
from utils.embed_builder import EmbedBuilder, MessageFormatter
from database_improved import db
from image_generator import image_gen

# Cargar variáveis de ambiente
load_dotenv()

# Configurar bot
config = BotConfig.from_env()
config.validate()

# Inicializar logging
logger = init_logging(config.debug_mode)

class StellarisBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
        self.config = config
        self.logger = logger
        self.ticket_counter = 0
        self._last_levelup_per_channel = {}
    
    def get_next_ticket_number(self):
        """Gera o próximo número de ticket formatado"""
        self.ticket_counter += 1
        return f"{self.ticket_counter:03d}"

bot = StellarisBot()

# ===== SISTEMA DE TICKETS (Melhorado) =====

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    async def on_timeout(self):
        """Chamado quando a view expira"""
        for item in self.children:
            item.disabled = True
        
        logger.logger.warning("TicketView timeout - disabling components")
    
    @discord.ui.select(
        placeholder="Selecione o tipo de ticket abaixo para começar!",
        custom_id="ticket_select",
        options=[
            discord.SelectOption(
                label="Ajuda",
                description="Para dúvidas, problemas ou solicitações gerais",
                emoji="❓"
            ),
            discord.SelectOption(
                label="Denúncia",
                description="Para reportar usuários ou situações problemáticas",
                emoji="🚨"
            ),
            discord.SelectOption(
                label="Sugestão",
                description="Para propor melhorias para o servidor",
                emoji="💡"
            )
        ]
    )
    async def ticket_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        user = interaction.user
        
        # Verificar se já tem ticket aberto
        existing_ticket = None
        if guild:
            for channel in guild.channels:
                if (isinstance(channel, discord.TextChannel) and 
                    f"-{user.display_name.lower().replace(' ', '-')}" in channel.name and 
                    channel.name.startswith("ticket-")):
                    existing_ticket = channel
                    break
        
        if existing_ticket:
            embed = EmbedBuilder.warning(
                "Ticket Já Existe",
                f"Você já possui um ticket aberto: {existing_ticket.mention}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        ticket_number = bot.get_next_ticket_number()
        ticket_name = f"ticket-{ticket_number}-{user.display_name.lower().replace(' ', '-')}"
        ticket_type = select.values[0]
        
        # Configurar permissões
        overwrites = {}
        if guild:
            overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=False)
            overwrites[user] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                attach_files=True,
                embed_links=True
            )
            if guild.me:
                overwrites[guild.me] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True
                )
        
        # Configurar cargo de suporte
        suporte_role = None
        category = None
        if guild:
            suporte_role = guild.get_role(config.suporte_role_id)
            if suporte_role:
                overwrites[suporte_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True
                )
            
            category = guild.get_channel(config.ticket_category_id)
        
        try:
            ticket_channel = None
            if guild:
                ticket_channel = await guild.create_text_channel(
                    name=ticket_name,
                    overwrites=overwrites,
                    category=category if isinstance(category, discord.CategoryChannel) else None,
                    topic=f"Ticket de {ticket_type} - {user.display_name}"
                )
            
            if ticket_channel:
                welcome_embed = EmbedBuilder.ticket_welcome(ticket_number, ticket_type, user)
                close_view = CloseTicketView()
                
                await ticket_channel.send(
                    content=f"{user.mention}",
                    embed=welcome_embed,
                    view=close_view
                )
                
                success_embed = EmbedBuilder.success(
                    "Ticket Criado",
                    f"Seu ticket foi criado: {ticket_channel.mention}"
                )
                await interaction.followup.send(embed=success_embed, ephemeral=True)
                
                logger.user_action(
                    str(user),
                    "CREATE_TICKET",
                    ticket_type,
                    ticket_number=ticket_number,
                    guild_id=guild.id
                )
        
        except discord.Forbidden:
            embed = EmbedBuilder.error(
                "Sem Permissão", 
                "Não tenho permissões para criar canais. Contate um administrador."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_occurred(e, "create_ticket", user_id=user.id)
            embed = EmbedBuilder.error("Erro", f"Erro ao criar ticket: {str(e)}")
            await interaction.followup.send(embed=embed, ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
    
    @discord.ui.button(label="🔒 Fechar Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        
        if not isinstance(channel, discord.TextChannel) or not channel.name.startswith("ticket-"):
            embed = EmbedBuilder.error("Canal Inválido", "Este comando só pode ser usado em canais de ticket.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        confirm_embed = EmbedBuilder.warning(
            "Confirmar Fechamento",
            "Tem certeza que deseja fechar este ticket?"
        )
        
        confirm_view = ConfirmCloseView()
        await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)

class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
    
    @discord.ui.button(label="✅ Sim, fechar", style=discord.ButtonStyle.danger, custom_id="confirm_close_yes")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        
        close_embed = EmbedBuilder.info(
            "Ticket Fechado",
            f"Ticket fechado por {interaction.user.mention}.\nO canal será deletado em 5 segundos."
        )
        close_embed.timestamp = discord.utils.utcnow()
        
        await interaction.response.send_message(embed=close_embed)
        
        logger.user_action(
            str(interaction.user),
            "CLOSE_TICKET", 
            channel.name,
            guild_id=interaction.guild.id
        )
        
        await asyncio.sleep(5)
        if isinstance(channel, discord.TextChannel):
            await channel.delete(reason=f"Ticket fechado por {interaction.user}")
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary, custom_id="confirm_close_no")
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = EmbedBuilder.success("Cancelado", "Fechamento cancelado.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== COMANDOS BÁSICOS (Melhorados) =====

@bot.tree.command(name="ping", description="Verifica se o bot está online")
@discord.app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    
    embed = EmbedBuilder.info(
        "Pong! 🏓",
        f"**Latência:** {latency}ms\n**Status:** Online ✅"
    )
    
    await interaction.response.send_message(embed=embed)
    logger.command_used(str(interaction.user), str(interaction.guild), "ping", latency=latency)

@bot.tree.command(name="oi", description="Cumprimente o bot")
@discord.app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
async def oi(interaction: discord.Interaction):
    embed = EmbedBuilder.info(
        "Olá! 👋",
        f"Olá, {interaction.user.mention}! Eu sou o bot da **Stell✦ris**, desenvolvido pela **Newy//Sh**.\n\n"
        "Use `/ajuda` para ver todos os meus comandos!"
    )
    
    if bot.user and bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)
    
    await interaction.response.send_message(embed=embed)
    logger.command_used(str(interaction.user), str(interaction.guild), "oi")

# ===== EVENTOS DO BOT (Melhorados) =====

@bot.event
async def on_ready():
    logger.logger.info(f'✅ Bot conectado como {bot.user}')
    logger.logger.info(f'🌐 Conectado em {len(bot.guilds)} servidor(s)')
    logger.logger.info(f'📋 Configurações do sistema de tickets:')
    logger.logger.info(f' Categoria ID: {config.ticket_category_id}')
    logger.logger.info(f' Cargo Suporte ID: {config.suporte_role_id}')
    
    # Conectar ao banco
    await db.connect()
    
    # Registrar views persistentes
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    
    # Sincronizar comandos
    try:
        synced = await bot.tree.sync()
        logger.logger.info(f'🔄 {len(synced)} comando(s) slash sincronizado(s)')
    except Exception as e:
        logger.error_occurred(e, "sync_commands")

@bot.event
async def on_disconnect():
    logger.logger.warning("⚠️ Bot desconectado do Discord - Tentando reconectar...")

@bot.event 
async def on_resumed():
    logger.logger.info("🔄 Conexão com Discord restaurada!")

@bot.event
async def on_connect():
    logger.logger.info("🔗 Conectando ao Discord...")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    
    await bot.process_commands(message)
    
    # Sistema de XP melhorado
    if len(message.content.strip()) > 0:
        xp_gain = random.randint(config.min_xp_gain, config.max_xp_gain)
        result = await db.add_xp(message.author.id, message.guild.id, xp_gain)
        
        if result and result.get('levelup') and not result.get('cooldown'):
            embed = EmbedBuilder.level_up(
                message.author, 
                result['old_level'], 
                result['new_level'], 
                result['xp_gained']
            )
            
            try:
                now = datetime.datetime.now()
                last_levelup = bot._last_levelup_per_channel.get(message.channel.id, datetime.datetime.min)
                
                # Evitar spam de level up (mínimo 5 segundos entre mensagens)
                if (now - last_levelup).total_seconds() >= 5:
                    levelup_msg = await message.channel.send(embed=embed)
                    bot._last_levelup_per_channel[message.channel.id] = now
                    
                    # Deletar mensagem após 10 segundos
                    await asyncio.sleep(10)
                    try:
                        await levelup_msg.delete()
                    except:
                        pass
            except Exception as e:
                logger.error_occurred(e, "levelup_message", user_id=message.author.id)

# ===== COMANDOS DIVERTIDOS =====

@bot.tree.command(name="dado", description="Rola um dado de 6 lados")
async def dado(interaction: discord.Interaction):
    numero = random.randint(1, 6)
    embed = EmbedBuilder.info("Dado 🎲", f"Você rolou o número **{numero}**!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="moeda", description="Joga uma moeda (cara ou coroa)")
async def moeda(interaction: discord.Interaction):
    resultado = random.choice(['Cara', 'Coroa'])
    embed = EmbedBuilder.info("Moeda 🪙", f"Deu: **{resultado}**!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tempo", description="Mostra a hora atual")
async def tempo(interaction: discord.Interaction):
    agora = datetime.datetime.now()
    embed = EmbedBuilder.info("Hora Atual 🕒", f"Agora são **{agora.strftime('%H:%M:%S')}** de {agora.strftime('%d/%m/%Y')}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="8ball", description="Faça uma pergunta para a bola mágica 8")
@discord.app_commands.describe(pergunta="Sua pergunta para a bola mágica")
async def eightball(interaction: discord.Interaction, pergunta: str):
    respostas = [
        "É certo", "É decididamente assim", "Sem dúvida", "Sim definitivamente",
        "Você pode contar com isso", "Como eu vejo, sim", "Provavelmente",
        "As perspectivas são boas", "Sim", "Os sinais apontam que sim",
        "Resposta nebulosa, tente novamente", "Pergunte novamente mais tarde",
        "Melhor não te contar agora", "Não posso prever agora",
        "Concentre-se e pergunte novamente", "Não conte com isso",
        "Minha resposta é não", "Minhas fontes dizem não",
        "As perspectivas não são tão boas", "Muito duvidoso"
    ]
    resposta = random.choice(respostas)
    embed = discord.Embed(title="🎱 Bola Mágica 8", color=0x9B59B6)
    embed.add_field(name="❓ Pergunta", value=pergunta, inline=False)
    embed.add_field(name="🔮 Resposta", value=f"*{resposta}*", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="escolher", description="Escolhe aleatoriamente entre opções")
@discord.app_commands.describe(opcoes="Opções separadas por vírgula (ex: pizza, hambúrguer, sushi)")
async def escolher(interaction: discord.Interaction, opcoes: str):
    lista_opcoes = [opcao.strip() for opcao in opcoes.split(",") if opcao.strip()]
    if len(lista_opcoes) < 2:
        await interaction.response.send_message("❌ Você precisa fornecer pelo menos 2 opções separadas por vírgula.", ephemeral=True)
        return
    escolha = random.choice(lista_opcoes)
    embed = EmbedBuilder.info("Escolha Aleatória 🎲", f"Entre as opções: **{', '.join(lista_opcoes)}**\n\n🎯 **Eu escolho: {escolha}**")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="reverse", description="Inverte o texto fornecido")
@discord.app_commands.describe(texto="Texto para inverter")
async def reverse(interaction: discord.Interaction, texto: str):
    embed = discord.Embed(title="🔄 Texto Invertido", color=0x3498DB)
    embed.add_field(name="📝 Original", value=texto, inline=False)
    embed.add_field(name="🔀 Invertido", value=texto[::-1], inline=False)
    await interaction.response.send_message(embed=embed)

# ===== COMANDOS DE INFORMAÇÃO =====

@bot.tree.command(name="avatar", description="Mostra o avatar de um usuário")
@discord.app_commands.describe(usuario="Usuário para ver o avatar (opcional)")
async def avatar(interaction: discord.Interaction, usuario: discord.Member = None):
    target = usuario or interaction.user
    embed = discord.Embed(title=f"🖼️ Avatar de {target.display_name}", color=0x3498DB)
    if target.avatar:
        embed.set_image(url=target.avatar.url)
        embed.add_field(name="Link direto", value=f"[Clique aqui]({target.avatar.url})", inline=False)
    else:
        embed.description = "Este usuário não possui um avatar personalizado."
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="Mostra informações sobre um usuário")
@discord.app_commands.describe(usuario="Usuário para ver informações (opcional)")
async def userinfo(interaction: discord.Interaction, usuario: discord.Member = None):
    target = usuario or interaction.user
    if not isinstance(target, discord.Member):
        await interaction.response.send_message("❌ Informações completas só estão disponíveis para membros do servidor.", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"👤 Informações de {target.display_name}",
        color=target.top_role.color if target.top_role.color != discord.Color.default() else discord.Color.blue()
    )
    embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
    embed.add_field(name="🆔 ID", value=target.id, inline=True)
    embed.add_field(name="📝 Nome", value=str(target), inline=True)
    embed.add_field(name="🏷️ Apelido", value=target.display_name, inline=True)
    embed.add_field(name="📅 Conta criada", value=target.created_at.strftime("%d/%m/%Y às %H:%M"), inline=True)
    embed.add_field(name="📥 Entrou no servidor", value=target.joined_at.strftime("%d/%m/%Y às %H:%M") if target.joined_at else "Desconhecido", inline=True)
    embed.add_field(name="🎭 Cargo mais alto", value=target.top_role.mention, inline=True)
    embed.add_field(name="🤖 Bot?", value="Sim" if target.bot else "Não", inline=True)
    embed.add_field(name="📊 Status", value=str(target.status).title(), inline=True)
    embed.add_field(name="🏅 Cargos", value=f"{len(target.roles) - 1}", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Mostra informações sobre o servidor")
async def serverinfo(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    guild = interaction.guild
    embed = discord.Embed(title=f"🏰 Informações de {guild.name}", color=0x3498DB)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="🆔 ID", value=guild.id, inline=True)
    embed.add_field(name="👑 Dono", value=guild.owner.mention if guild.owner else "Desconhecido", inline=True)
    embed.add_field(name="📅 Criado em", value=guild.created_at.strftime("%d/%m/%Y às %H:%M"), inline=True)
    embed.add_field(name="👥 Membros", value=guild.member_count, inline=True)
    embed.add_field(name="💬 Canais", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Cargos", value=len(guild.roles), inline=True)
    embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
    embed.add_field(name="🔒 Verificação", value=str(guild.verification_level).title(), inline=True)
    embed.add_field(name="🛡️ Filtro", value=str(guild.explicit_content_filter).title(), inline=True)
    await interaction.response.send_message(embed=embed)

# ===== COMANDOS DE MODERAÇÃO =====

@bot.tree.command(name="limpar", description="Apaga mensagens do canal atual")
@discord.app_commands.describe(quantidade="Quantidade de mensagens para apagar (máximo 100)")
async def limpar(interaction: discord.Interaction, quantidade: int):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Você precisa da permissão 'Gerenciar Mensagens'.", ephemeral=True)
        return
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("❌ Este comando só pode ser usado em canais de texto.", ephemeral=True)
        return
    if quantidade < 1 or quantidade > 100:
        await interaction.response.send_message("❌ A quantidade deve ser entre 1 e 100.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=quantidade)
        await interaction.followup.send(f"✅ {len(deleted)} mensagem(s) apagada(s) com sucesso!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Não tenho permissão para apagar mensagens.", ephemeral=True)

@bot.tree.command(name="ban", description="Bane um usuário do servidor")
@discord.app_commands.describe(usuario="Usuário para banir", motivo="Motivo do banimento")
async def ban(interaction: discord.Interaction, usuario: discord.Member, motivo: str = "Não especificado"):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Você precisa da permissão 'Banir Membros'.", ephemeral=True)
        return
    if usuario == interaction.user:
        await interaction.response.send_message("❌ Você não pode banir a si mesmo.", ephemeral=True)
        return
    if usuario.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Você não pode banir alguém com cargo igual ou superior ao seu.", ephemeral=True)
        return
    try:
        await usuario.ban(reason=f"Banido por {interaction.user} - {motivo}")
        embed = EmbedBuilder.moderation_action("ban", usuario, interaction.user, motivo)
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para banir este usuário.", ephemeral=True)

@bot.tree.command(name="kick", description="Expulsa um usuário do servidor")
@discord.app_commands.describe(usuario="Usuário para expulsar", motivo="Motivo da expulsão")
async def kick(interaction: discord.Interaction, usuario: discord.Member, motivo: str = "Não especificado"):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ Você precisa da permissão 'Expulsar Membros'.", ephemeral=True)
        return
    if usuario == interaction.user:
        await interaction.response.send_message("❌ Você não pode expulsar a si mesmo.", ephemeral=True)
        return
    if usuario.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Você não pode expulsar alguém com cargo igual ou superior ao seu.", ephemeral=True)
        return
    try:
        await usuario.kick(reason=f"Expulso por {interaction.user} - {motivo}")
        embed = EmbedBuilder.moderation_action("kick", usuario, interaction.user, motivo)
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para expulsar este usuário.", ephemeral=True)

@bot.tree.command(name="timeout", description="Dá timeout em um usuário")
@discord.app_commands.describe(usuario="Usuário para dar timeout", minutos="Duração em minutos (máx 40320)", motivo="Motivo do timeout")
async def timeout_cmd(interaction: discord.Interaction, usuario: discord.Member, minutos: int, motivo: str = "Não especificado"):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Você precisa da permissão 'Moderar Membros'.", ephemeral=True)
        return
    if usuario == interaction.user:
        await interaction.response.send_message("❌ Você não pode dar timeout em si mesmo.", ephemeral=True)
        return
    if usuario.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Você não pode dar timeout em alguém com cargo igual ou superior ao seu.", ephemeral=True)
        return
    if minutos < 1 or minutos > 40320:
        await interaction.response.send_message("❌ A duração deve ser entre 1 e 40320 minutos.", ephemeral=True)
        return
    try:
        await usuario.timeout(datetime.timedelta(minutes=minutos), reason=f"Timeout por {interaction.user} - {motivo}")
        embed = EmbedBuilder.moderation_action("timeout", usuario, interaction.user, f"{motivo} ({minutos} min)")
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para dar timeout neste usuário.", ephemeral=True)

# ===== COMANDOS UTILITÁRIOS =====

@bot.tree.command(name="say", description="Faz o bot dizer algo")
@discord.app_commands.describe(mensagem="Mensagem para o bot falar")
async def say(interaction: discord.Interaction, mensagem: str):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Você precisa da permissão 'Gerenciar Mensagens'.", ephemeral=True)
        return
    mensagem = MessageFormatter.sanitize_mentions(mensagem)
    await interaction.response.send_message(mensagem)

@bot.tree.command(name="embed", description="Cria um embed personalizado")
@discord.app_commands.describe(titulo="Título do embed", descricao="Descrição do embed", cor="Cor em hexadecimal (ex: #ff0000)")
async def embed_command(interaction: discord.Interaction, titulo: str, descricao: str, cor: str = None):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Você precisa da permissão 'Gerenciar Mensagens'.", ephemeral=True)
        return
    try:
        embed_color = discord.Color.blue()
        if cor:
            cor = cor.lstrip('#')
            if len(cor) == 6 and all(c in '0123456789abcdefABCDEF' for c in cor):
                embed_color = discord.Color(int(cor, 16))
        embed = discord.Embed(title=titulo, description=descricao, color=embed_color, timestamp=datetime.datetime.now())
        embed.set_footer(text=f"Criado por {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao criar embed: {str(e)}", ephemeral=True)

@bot.tree.command(name="ticket_setup", description="Configura o sistema de tickets em um canal (Admin)")
@discord.app_commands.describe(canal="Canal onde configurar o sistema de tickets (opcional)")
async def ticket_setup(interaction: discord.Interaction, canal: discord.TextChannel = None):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Você precisa de permissões de administrador.", ephemeral=True)
        return
    try:
        target_canal = canal or (interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None)
        if not target_canal:
            await interaction.response.send_message("❌ Este comando deve ser usado em um canal de texto.", ephemeral=True)
            return
        if interaction.guild and interaction.guild.me:
            perms = target_canal.permissions_for(interaction.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await interaction.response.send_message("❌ Não tenho permissões para enviar mensagens ou embeds neste canal.", ephemeral=True)
                return
        embed = discord.Embed(
            title="🎫 Bem-vindo ao sistema de tickets!",
            description=(
                "• **Ajuda:** Para dúvidas, problemas ou solicitações gerais\n"
                "• **Denúncia:** Para reportar usuários ou situações problemáticas\n"
                "• **Sugestão:** Para propor melhorias para o servidor\n\n"
                "**Orientações importantes:**\n"
                "• Antes de abrir um ticket, verifique se sua dúvida já não foi respondida nas regras ou canais fixos.\n"
                "• Ao abrir um ticket, explique seu motivo de forma clara e educada.\n"
                "• O uso indevido do sistema pode resultar em punição.\n\n"
                "**Selecione abaixo o tipo de ticket que você deseja abrir:**"
            ),
            color=0x3498DB
        )
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text="💜 Stell✦ris Bot - Sistema de Tickets")
        await target_canal.send(embed=embed, view=TicketView())
        await interaction.response.send_message(f"✅ Sistema de tickets configurado em {target_canal.mention}!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissões para enviar mensagens neste canal.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {str(e)}", ephemeral=True)

# ===== SISTEMA DE NÍVEIS - COMANDOS =====

@bot.tree.command(name="level", description="Mostra seu nível atual ou de outro usuário")
@discord.app_commands.describe(usuario="Usuário para ver o nível (opcional)")
async def level(interaction: discord.Interaction, usuario: discord.Member = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    target = usuario or interaction.user
    if not isinstance(target, discord.Member):
        await interaction.response.send_message("❌ Usuário inválido.", ephemeral=True)
        return
    user_data = await db.get_user_data(target.id, interaction.guild.id)
    rank = await db.get_user_rank(target.id, interaction.guild.id)
    current_level = user_data['level']
    current_xp = user_data['xp']
    xp_for_current = db.xp_for_level(current_level)
    xp_for_next = db.xp_for_level(current_level + 1)
    xp_in_level = current_xp - xp_for_current
    xp_needed = xp_for_next - xp_for_current
    progress_percent = (xp_in_level / xp_needed) * 100 if xp_needed > 0 else 100
    filled = int(20 * (progress_percent / 100))
    progress_bar = "█" * filled + "░" * (20 - filled)
    embed = discord.Embed(title=f"📊 Nível de {target.display_name}", color=discord.Color.from_str(user_data.get('favorite_color', '#7289DA')))
    embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
    embed.add_field(name="🏆 Nível", value=f"**{current_level}**", inline=True)
    embed.add_field(name="📈 Ranking", value=f"**#{rank}**", inline=True)
    embed.add_field(name="💫 XP Total", value=f"{current_xp:,}", inline=True)
    embed.add_field(name="📊 Progresso", value=f"{xp_in_level:,} / {xp_needed:,} XP", inline=True)
    embed.add_field(name="🎯 Próximo Nível", value=f"{progress_percent:.1f}%", inline=True)
    embed.add_field(name="💬 Mensagens", value=f"{user_data['messages_sent']:,}", inline=True)
    embed.add_field(name="📈 Barra de Progresso", value=f"`{progress_bar}`", inline=False)
    await interaction.response.send_message(embed=embed)
    logger.command_used(str(interaction.user), str(interaction.guild), "level")

@bot.tree.command(name="rank", description="Mostra o ranking do servidor")
@discord.app_commands.describe(pagina="Página do ranking (cada página tem 10 usuários)")
async def rank(interaction: discord.Interaction, pagina: int = 1):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    if pagina < 1:
        pagina = 1
    offset = (pagina - 1) * 10
    leaderboard = await db.get_leaderboard(interaction.guild.id, limit=10)
    if not leaderboard:
        await interaction.response.send_message("❌ Ainda não há dados de ranking neste servidor.", ephemeral=True)
        return
    embed = discord.Embed(title=f"🏆 Ranking - {interaction.guild.name}", description=f"📄 Página {pagina}", color=discord.Color.gold())
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    medals = ["🥇", "🥈", "🥉"]
    ranking_text = ""
    for i, user_data in enumerate(leaderboard):
        position = offset + i + 1
        user = interaction.guild.get_member(user_data['user_id'])
        if user:
            medal = medals[i] if i < 3 and pagina == 1 else f"**{position}.**"
            name = user.display_name[:15] + "..." if len(user.display_name) > 15 else user.display_name
            ranking_text += f"{medal} {name}\n    Nível: **{user_data['level']}** • XP: **{user_data['xp']:,}**\n\n"
    embed.description += f"\n\n{ranking_text}"
    embed.set_footer(text="Use /rank pagina:<número> para ver outras páginas")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="profile", description="Mostra o profile completo com banner personalizado")
@discord.app_commands.describe(usuario="Usuário para ver o profile (opcional)")
async def profile(interaction: discord.Interaction, usuario: discord.Member = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    target = usuario or interaction.user
    if not isinstance(target, discord.Member):
        await interaction.response.send_message("❌ Usuário inválido.", ephemeral=True)
        return
    await interaction.response.defer()
    try:
        user_data = await db.get_user_data(target.id, interaction.guild.id)
        rank_pos = await db.get_user_rank(target.id, interaction.guild.id)
        profile_image = await image_gen.generate_profile_image(user_data, target, rank_pos)
        file = discord.File(profile_image, filename=f"profile_{target.id}.png")
        embed = discord.Embed(title=f"📊 Profile de {target.display_name}", color=discord.Color.from_str(user_data.get('favorite_color', '#7289DA')))
        embed.set_image(url=f"attachment://profile_{target.id}.png")
        bio = user_data.get('bio')
        if bio:
            embed.add_field(name="📝 Bio", value=bio[:1024], inline=False)
        embed.set_footer(text="Use /setbanner para personalizar seu banner!")
        await interaction.followup.send(embed=embed, file=file)
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao gerar profile: {str(e)}", ephemeral=True)

# ===== COMANDOS DE PERSONALIZAÇÃO =====

@bot.tree.command(name="setbanner", description="Escolha entre 20 banners únicos ou use URL personalizada para seu profile")
@discord.app_commands.describe(opcao="Escolha um banner predefinido ou 'personalizado' para URL própria", url="URL da imagem (apenas se escolher 'personalizado')")
@discord.app_commands.choices(opcao=[
    discord.app_commands.Choice(name="🌌 Galáxia Espacial", value="space"),
    discord.app_commands.Choice(name="⭐ Dark Stars", value="stars"),
    discord.app_commands.Choice(name="🎨 Blue Abstract", value="abstract_blue"),
    discord.app_commands.Choice(name="🌸 Pink Abstract", value="abstract_pink"),
    discord.app_commands.Choice(name="📱 Discord Type", value="discord"),
    discord.app_commands.Choice(name="✨ Minimalista", value="minimal"),
    discord.app_commands.Choice(name="❤ Catto", value="anime"),
    discord.app_commands.Choice(name="🌷 Floral Cute", value="cute_floral"),
    discord.app_commands.Choice(name="🤍 Whitish", value="kpop_bts"),
    discord.app_commands.Choice(name="🎮 Roblox", value="roblox"),
    discord.app_commands.Choice(name="💜 Purple Abstract", value="abstract_purple"),
    discord.app_commands.Choice(name="✩ Star", value="cute_pastel"),
    discord.app_commands.Choice(name="📺 Random", value="youtube_style"),
    discord.app_commands.Choice(name="🦋 White Forest", value="neon_blue"),
    discord.app_commands.Choice(name="❦ Grimm", value="cherry_blossom"),
    discord.app_commands.Choice(name="🎭 Artistic", value="artistic"),
    discord.app_commands.Choice(name="🌙 Dark Minimalism", value="dark_minimal"),
    discord.app_commands.Choice(name="✞ Angel", value="mystic"),
    discord.app_commands.Choice(name="❀ Retro Blossom", value="kawaii_pink"),
    discord.app_commands.Choice(name="✦ Monotone", value="twitter_style"),
    discord.app_commands.Choice(name="🔗 URL Personalizada", value="personalizado"),
])
async def setbanner(interaction: discord.Interaction, opcao: str, url: str = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    banners_predefinidos = {
        "space": "banners/Space_1757594370395.jpeg",
        "stars": "banners/☆_1757594393934.jpeg",
        "abstract_blue": "banners/40bc4447-217e-4dc3-ab7d-655885da45d8_1757594374395.jpeg",
        "abstract_pink": "banners/c8ef8815-07bf-41f4-a789-d18f5cdca9f6_1757594473987.jpeg",
        "discord": "banners/discord banner_1757594381102.jpeg",
        "minimal": "banners/__1757594377705.jpeg",
        "anime": "banners/One Shots __S!Male reader x Characters___1757594404454.jpeg",
        "cute_floral": "banners/(つ﹏_ _ 𝗛𝗘𝗔𝗗𝗘𝗥𝗦 _! 🌷_1757595516769.jpeg",
        "kpop_bts": "banners/¡ 𝐈𝐂𝐎𝐍𝐒 !  - bts packs 2 ¡!_1757595522435.jpeg",
        "roblox": "banners/#Old #Roblox #Роблокс_1757595528755.jpeg",
        "abstract_purple": "banners/Fundo De Banner De Pincel De Pintura Abstrato Roxo, Roxa, Pincel De Pintura Abstrato, Bandeira Imagem de plano de fundo para download gratuito_1757595782159.jpeg",
        "cute_pastel": "banners/Cute Background for Your Next Project_1757595800718.jpeg",
        "youtube_style": "banners/Banner YouTube 2560 x 1440 pixels_1757595804524.jpeg",
        "neon_blue": "banners/0f3e72e6-604d-494f-a42a-801fdb6081e5_1757595525560.jpeg",
        "cherry_blossom": "banners/10fcfa26-b1da-43c0-a0f2-78ad91412e4e_1757595590598.jpeg",
        "artistic": "banners/67d49c3a-467d-4138-90de-d84d25c3ea40_1757595797377.jpeg",
        "dark_minimal": "banners/857522af-3e81-43ad-a878-77d528bdd90f_1757595789465.jpeg",
        "mystic": "banners/⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣿⣼⡀⠀⠀⠀⠀⠀⠀⣀⣴⣱⠁…_1757595793709.jpeg",
        "kawaii_pink": "banners/psicobaby_1757595808356.jpeg",
        "twitter_style": "banners/@Petit_Cossette_ on twitter_1757595593972.jpeg",
    }
    nome_banners = {
        "space": "🌌 Galáxia Espacial", "stars": "⭐ Dark Stars", "abstract_blue": "🎨 Blue Abstract",
        "abstract_pink": "🌸 Pink Abstract", "discord": "📱 Discord Type", "minimal": "✨ Minimalista",
        "anime": "❤ Catto", "cute_floral": "🌷 Floral Cute", "kpop_bts": "🤍 Whitish",
        "roblox": "🎮 Roblox", "abstract_purple": "💜 Purple Abstract", "cute_pastel": "✩ Star",
        "youtube_style": "📺 Random", "neon_blue": "🦋 White Forest", "cherry_blossom": "❦ Grimm",
        "artistic": "🎭 Artistic", "dark_minimal": "🌙 Dark Minimalism", "mystic": "✞ Angel",
        "kawaii_pink": "❀ Retro Blossom", "twitter_style": "✦ Monotone",
    }
    try:
        if opcao == "personalizado":
            if not url:
                await interaction.response.send_message("❌ Você deve fornecer uma URL quando escolher 'personalizado'.", ephemeral=True)
                return
            if not url.startswith('https://'):
                await interaction.response.send_message("❌ Por favor, forneça uma URL HTTPS válida.", ephemeral=True)
                return
            valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
            if not any(url.lower().endswith(ext) for ext in valid_extensions):
                await interaction.response.send_message("❌ A URL deve apontar para uma imagem (.png, .jpg, .jpeg, .gif, .webp)", ephemeral=True)
                return
            await interaction.response.defer()
            test_image = image_gen.download_image(url)
            if not test_image:
                await interaction.followup.send("❌ Não foi possível acessar a imagem. Verifique se a URL está correta.", ephemeral=True)
                return
            banner_path = url
            banner_name = "Personalizado"
        else:
            if opcao not in banners_predefinidos:
                await interaction.response.send_message("❌ Opção de banner inválida.", ephemeral=True)
                return
            banner_path = banners_predefinidos[opcao]
            banner_name = nome_banners.get(opcao, "Banner Predefinido")
            await interaction.response.defer()
        await db.update_banner(interaction.user.id, interaction.guild.id, banner_path)
        embed = EmbedBuilder.success("Banner Atualizado!", f"Banner **{banner_name}** definido com sucesso!\nUse `/profile` para ver como ficou.")
        if opcao == "personalizado":
            embed.set_image(url=url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Erro ao definir banner: {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Erro ao definir banner: {str(e)}", ephemeral=True)

@bot.tree.command(name="setbio", description="Define uma bio personalizada para seu profile")
@discord.app_commands.describe(bio="Sua bio personalizada (máximo 200 caracteres)")
async def setbio(interaction: discord.Interaction, bio: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    if len(bio) > 200:
        await interaction.response.send_message("❌ A bio deve ter no máximo 200 caracteres.", ephemeral=True)
        return
    try:
        await db.update_bio(interaction.user.id, interaction.guild.id, bio)
        embed = EmbedBuilder.success("Bio Atualizada!", f"Sua bio foi definida como:\n\n*{bio}*\n\nUse `/profile` para ver seu profile completo!")
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao definir bio: {str(e)}", ephemeral=True)

@bot.tree.command(name="setcolor", description="Define sua cor favorita para o profile")
@discord.app_commands.describe(cor="Cor em formato hexadecimal (ex: #ff0000 para vermelho)")
async def setcolor(interaction: discord.Interaction, cor: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    cor = cor.strip().upper()
    if not cor.startswith('#'):
        cor = '#' + cor
    if len(cor) != 7:
        await interaction.response.send_message("❌ A cor deve estar no formato hexadecimal (#rrggbb). Exemplo: #FF0000", ephemeral=True)
        return
    try:
        color_value = int(cor[1:], 16)
        if color_value < 0x111111:
            await interaction.response.send_message("❌ Cor muito escura. Escolha uma cor mais clara.", ephemeral=True)
            return
    except ValueError:
        await interaction.response.send_message("❌ Cor inválida. Use apenas caracteres hexadecimais (0-9, A-F).", ephemeral=True)
        return
    try:
        await db.update_favorite_color(interaction.user.id, interaction.guild.id, cor)
        embed = EmbedBuilder.success("Cor Favorita Atualizada!", f"Sua cor favorita foi definida para `{cor}`\n\nUse `/profile` para ver como ficou!")
        embed.color = discord.Color.from_str(cor)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao definir cor: {str(e)}", ephemeral=True)

# ===== COMANDO DE AJUDA =====

@bot.tree.command(name="ajuda", description="Mostra todos os comandos disponíveis do bot")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Comandos do Stell✦ris Bot",
        description="Aqui estão todos os comandos slash disponíveis!",
        color=0x9B59B6
    )
    embed.add_field(name="🎯 Básicos", value="/ping • /oi • /ajuda", inline=False)
    embed.add_field(name="🎮 Divertidos", value="/dado • /moeda • /tempo • /8ball • /escolher • /avatar • /reverse", inline=False)
    embed.add_field(name="📊 Informação", value="/userinfo • /serverinfo", inline=False)
    embed.add_field(name="🛡️ Moderação", value="/limpar • /ban • /kick • /timeout", inline=False)
    embed.add_field(name="🔧 Utilitários", value="/say • /embed", inline=False)
    embed.add_field(name="📈 Níveis", value="/level • /rank • /profile", inline=False)
    embed.add_field(name="🎨 Personalização", value="/setbanner • /setbio • /setcolor", inline=False)
    embed.add_field(name="🎫 Tickets", value="/ticket_setup (Admin)", inline=False)
    embed.add_field(name="📜 Regras", value="/setrules (Admin)", inline=False)
    if bot.user and bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(text="💜 Stell✦ris Bot - Desenvolvido pela Newy//Sh")
    await interaction.response.send_message(embed=embed)

# ===== COMANDO /SEND - ENVIAR REGRAS =====

@bot.tree.command(name="setrules", description="Envia as regras do servidor no canal atual")
async def send_rules(interaction: discord.Interaction):
    """Envia as regras formatadas no canal (apenas administradores)"""
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
        embed = EmbedBuilder.error("Sem Permissão", "Você precisa ser administrador para usar este comando.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    canal = interaction.channel

    # Verificar se o bot tem permissão para enviar no canal
    if isinstance(canal, discord.TextChannel) and interaction.guild and interaction.guild.me:
        perms = canal.permissions_for(interaction.guild.me)
        if not perms.send_messages or not perms.embed_links or not perms.attach_files:
            await interaction.response.send_message(
                "❌ Não tenho permissão para enviar mensagens, embeds ou arquivos neste canal. "
                "Dê ao bot a permissão de **Enviar Mensagens**, **Incorporar Links** e **Anexar Arquivos**.",
                ephemeral=True
            )
            return

    await interaction.response.send_message("✅ Enviando regras...", ephemeral=True)

    try:
        # 1ª mensagem: banner como arquivo local
        banner_path = os.path.join(os.path.dirname(__file__), "attached_assets", "e4cbadda-c7ae-4194-bfbf-5cf816f5002e_1782100554351.jpeg")
        banner_file = discord.File(banner_path, filename="banner.jpeg")
        embed_banner = discord.Embed(color=0x000000)
        embed_banner.set_image(url="attachment://banner.jpeg")
        await canal.send(file=banner_file, embed=embed_banner)

        # 2ª mensagem: regras
        embed_regras = discord.Embed(title="📜 Regras do Servidor", color=0x9B59B6)
        embed_regras.add_field(
            name="",
            value=(
                ":one:┃**Spam / Floods / Crash Gifs**\n"
                "Use o bom senso. Evite enviar mensagens repetitivas, em grande quantidade de uma vez ou gifs que possam causar travamentos (incluindo emojis animados em excesso).\n\n"
                ":two:┃**Divulgação e Comércio**\n"
                "Não é permitido divulgar outros servidores do Discord ou realizar transações de qualquer tipo (vendas, trocas, produtos, serviços) dentro do servidor, seja em canais públicos ou DMs. Isso inclui transações envolvendo contas, skins, produtos digitais ou outros itens."
            ),
            inline=False
        )
        embed_regras.add_field(
            name="",
            value=(
                ":three:┃**Informações Pessoais**\n"
                "Para a segurança de todos, não compartilhe ou solicite informações pessoais, como idade, fotos, endereço, número de telefone, RA, senha, CPF ou quaisquer dados que possam expor você ou outros membros.\n\n"
                ":four:┃**Evasão de Punição**\n"
                "Não utilize contas alternativas para burlar banimentos ou mutes. A violação dessa regra resultará em banimento permanente, sem possibilidade de apelação."
            ),
            inline=False
        )
        embed_regras.add_field(
            name="",
            value=(
                ":five:┃**Conteúdo Explícito ou Malicioso**\n"
                "É proibido o envio de conteúdo explícito ou malicioso que cause desconforto ou prejudique os membros, incluindo imagens, vídeos, avatares, banners ou links com material impróprio (como gore ou pornografia), arquivos maliciosos, iploggers, links de scam, golpes de nitro ou qualquer outro conteúdo prejudicial."
            ),
            inline=False
        )
        embed_regras.add_field(
            name="",
            value=(
                ":six:┃**Desrespeito**\n"
                "Não é permitido desrespeitar membros ou moderadores, praticar discriminação de qualquer natureza (religião, identidade de gênero, condição física, racismo, sexualidade, xenofobia ou discurso de ódio). Também são proibidos trolls, ameaças, comportamento agressivo, passivo-agressivo ou mal-intencionado."
            ),
            inline=False
        )
        await canal.send(embed=embed_regras)

        # 3ª mensagem: punições
        embed_punicoes = discord.Embed(
            title="⚠️ Punições por Quebra de Regras",
            description=(
                "1️⃣┃Mute de 5-10 minutos, pode ter duração maior dependendo da gravidade e intenção. 1 aviso será contabilizado à sua conta do servidor.\n\n"
                "2️⃣┃Mesmas punições que a regra 1, diferenças: maior tempo de mute e 2 avisos contabilizados.\n\n"
                "3️⃣┃Você terá que arcar com as consequências se algo for realizado usando as informações que você não deveria ter providenciado.\n\n"
                "4️⃣┃Banimento sem exceção.\n\n"
                "5️⃣┃Conteúdo indevido: Mute + 2 avisos, scam: Banimento + denúncias.\n\n"
                "6️⃣┃Mute ou banimento dependendo do quão grave for a situação.\n\n"
                "**Sistema de avisos:** seus avisos serão contabilizados. Se você acumular 3 avisos, receberá um banimento. "
                "Punições ficam mais severas de acordo com a gravidade da regra quebrada."
            ),
            color=0x9B59B6
        )
        await canal.send(embed=embed_punicoes)

        logger.command_used(str(interaction.user), str(interaction.guild), "setrules")

    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Não tenho permissão para enviar mensagens neste canal. "
            "Verifique as permissões do bot (**Enviar Mensagens**, **Incorporar Links**, **Anexar Arquivos**).",
            ephemeral=True
        )
    except Exception as e:
        logger.error_occurred(e, "setrules", user_id=interaction.user.id)
        await interaction.followup.send(f"❌ Erro ao enviar regras: {str(e)}", ephemeral=True)

# ===== COMANDO DE SINCRONIZAÇÃO (Melhorado) =====

@bot.command()
async def sync(ctx):
    """Comando para sincronizar slash commands (apenas para administradores)"""
    if ctx.author.id not in config.admin_ids:
        embed = EmbedBuilder.error("Sem Permissão", "Você não tem permissão para usar este comando.")
        await ctx.send(embed=embed)
        return
    
    try:
        synced = await bot.tree.sync()
        embed = EmbedBuilder.success(
            "Comandos Sincronizados",
            f"{len(synced)} comando(s) sincronizado(s) com sucesso!"
        )
        await ctx.send(embed=embed)
        logger.command_used(str(ctx.author), str(ctx.guild), "sync", synced_count=len(synced))
    except Exception as e:
        logger.error_occurred(e, "sync_command", user_id=ctx.author.id)
        embed = EmbedBuilder.error("Erro", f"Erro ao sincronizar: {e}")
        await ctx.send(embed=embed)

# ===== HANDLER DE ERROS GLOBAL =====

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """Handler global de erros para comandos slash"""
    
    if isinstance(error, discord.app_commands.MissingPermissions):
        embed = EmbedBuilder.error("Sem Permissão", "Você não tem permissões para usar este comando.")
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        embed = EmbedBuilder.error("Bot Sem Permissão", "Eu não tenho as permissões necessárias para executar este comando.")
    elif isinstance(error, discord.app_commands.CommandOnCooldown):
        embed = EmbedBuilder.warning(
            "Comando em Cooldown", 
            f"Aguarde {error.retry_after:.2f} segundos antes de usar este comando novamente."
        )
    elif isinstance(error, discord.app_commands.CheckFailure):
        embed = EmbedBuilder.warning("Verificação Falhada", "Você não atende aos requisitos para usar este comando.")
    else:
        logger.error_occurred(
            error, 
            "app_command_error",
            command=interaction.command.name if interaction.command else "unknown",
            user_id=interaction.user.id,
            guild_id=interaction.guild.id if interaction.guild else None
        )
        embed = EmbedBuilder.error("Erro Inesperado", "Ocorreu um erro inesperado. Tente novamente em alguns instantes.")
    
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    except:
        pass  # Falha silenciosa se não conseguir enviar a mensagem

# ===== TRATAMENTO DE SHUTDOWN GRACIOSO =====

async def shutdown_handler():
    """Fecha conexões graciosamente"""
    logger.logger.info("🔄 Iniciando shutdown gracioso...")
    
    try:
        await db.close()
        logger.logger.info("✅ Shutdown completo")
    except Exception as e:
        logger.error_occurred(e, "shutdown")

import signal
import atexit

def signal_handler(signum, frame):
    """Handler para sinais do sistema"""
    logger.logger.info(f"📡 Sinal recebido: {signum}")
    asyncio.create_task(shutdown_handler())

# Registrar handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(lambda: asyncio.run(shutdown_handler()) if not bot.is_closed() else None)

# ===== SERVIDOR KEEP-ALIVE (para hosting gratuito) =====

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Stell\xe2\x9c\xa6ris Bot is alive!")

    def log_message(self, format, *args):
        pass  # silencia os logs do servidor HTTP

def run_keep_alive():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), KeepAliveHandler)
    server.serve_forever()

def start_keep_alive():
    t = threading.Thread(target=run_keep_alive, daemon=True)
    t.start()

# ===== INICIALIZAÇÃO =====

if __name__ == "__main__":
    start_keep_alive()
    try:
        bot.run(config.discord_token)
    except KeyboardInterrupt:
        logger.logger.info("👋 Bot encerrado manualmente pelo usuário")
    except Exception as e:
        logger.error_occurred(e, "bot_startup")
        raise
