from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests
import io
import os
from typing import Optional, Dict
import math

class ProfileImageGenerator:
    def __init__(self):
        self.base_width = 800
        self.base_height = 400
        self.avatar_size = 120
        self.min_banner_height = 160
        self.max_banner_height = 280
        
    def is_safe_url(self, url: str) -> bool:
        """Verifica se a URL é segura contra SSRF"""
        try:
            import urllib.parse
            import socket
            import ipaddress
            
            parsed = urllib.parse.urlparse(url)
            
            if parsed.scheme != 'https':
                return False
            
            hostname = parsed.hostname
            if not hostname:
                return False
            
            clean_hostname = hostname.strip('[]')
            
            try:
                addr_info = socket.getaddrinfo(clean_hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                
                for family, _, _, _, sockaddr in addr_info:
                    ip_str = sockaddr[0]
                    try:
                        ip_obj = ipaddress.ip_address(ip_str)
                        
                        if (ip_obj.is_private or 
                            ip_obj.is_loopback or 
                            ip_obj.is_multicast or 
                            ip_obj.is_reserved or 
                            ip_obj.is_link_local):
                            return False
                        
                        if isinstance(ip_obj, ipaddress.IPv6Address):
                            if ip_obj.is_site_local:
                                return False
                            if str(ip_obj).startswith(('fe80:', 'fc00:', 'fd00:')):
                                return False
                        
                        if isinstance(ip_obj, ipaddress.IPv4Address):
                            if str(ip_obj).startswith(('169.254.', '127.', '10.', '172.', '192.168.')):
                                return False
                                
                    except ipaddress.AddressValueError:
                        continue
                        
            except (socket.gaierror, socket.error):
                return False
            
            return True
            
        except Exception:
            return False
    
    def download_image(self, url: str) -> Optional[Image.Image]:
        """Baixa uma imagem da URL com validações de segurança"""
        try:
            if not self.is_safe_url(url):
                return None
            
            current_url = url
            max_redirects = 2
            redirect_count = 0
            
            while redirect_count <= max_redirects:
                head_response = requests.head(
                    current_url, 
                    timeout=5,
                    allow_redirects=False,
                    headers={'User-Agent': 'Discord-Bot-Image-Fetcher/1.0'}
                )
                
                if head_response.status_code in (301, 302, 303, 307, 308):
                    if redirect_count >= max_redirects:
                        return None
                    
                    redirect_url = head_response.headers.get('Location')
                    if not redirect_url:
                        return None
                    
                    import urllib.parse
                    redirect_url = urllib.parse.urljoin(current_url, redirect_url)
                    
                    if not self.is_safe_url(redirect_url):
                        return None
                    
                    current_url = redirect_url
                    redirect_count += 1
                    continue
                    
                elif head_response.status_code != 200:
                    return None
                
                content_length = head_response.headers.get('Content-Length')
                if content_length and int(content_length) > 5 * 1024 * 1024:
                    return None
                
                break
            
            if not self.is_safe_url(current_url):
                return None
            
            response = requests.get(
                current_url, 
                timeout=8,
                stream=True,
                allow_redirects=False,
                headers={'User-Agent': 'Discord-Bot-Image-Fetcher/1.0'}
            )
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                return None
            
            content = b''
            max_size = 5 * 1024 * 1024
            for chunk in response.iter_content(chunk_size=4096):
                content += chunk
                if len(content) > max_size:
                    return None
            
            if len(content) < 100:
                return None
            
            img = Image.open(io.BytesIO(content))
            
            if img.format not in ['JPEG', 'PNG', 'GIF', 'WEBP']:
                return None
            
            img.load()
            
            if img.size[0] > 2000 or img.size[1] > 2000:
                return None
            
            return img
            
        except Exception as e:
            print(f"Erro ao baixar imagem: {e}")
            return None
    
    def load_local_image(self, file_path: str) -> Optional[Image.Image]:
        """Carrega uma imagem do arquivo local com validações"""
        try:
            if not os.path.exists(file_path):
                print(f"Arquivo não encontrado: {file_path}")
                return None
            
            img = Image.open(file_path)
            
            if img.format not in ['JPEG', 'PNG', 'GIF', 'WEBP']:
                print(f"Formato de imagem não suportado: {img.format}")
                return None
            
            img.load()
            
            if img.size[0] > 4000 or img.size[1] > 4000:
                print(f"Imagem muito grande: {img.size}")
                return None
            
            return img
            
        except Exception as e:
            print(f"Erro ao carregar imagem local: {e}")
            return None
    
    def load_image(self, path_or_url: str) -> Optional[Image.Image]:
        """Carrega uma imagem seja ela local ou de URL"""
        if path_or_url.startswith(('http://', 'https://')):
            return self.download_image(path_or_url)
        else:
            return self.load_local_image(path_or_url)
    
    def create_rounded_mask(self, size: tuple, radius: int) -> Image.Image:
        """Cria uma máscara arredondada"""
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, size[0], size[1]], radius, fill=255)
        return mask
    
    def hex_to_rgb(self, hex_color: str) -> tuple:
        """Converte cor hexadecimal para RGB"""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (114, 137, 218)
    
    def get_level_color(self, level: int) -> str:
        """Retorna uma cor baseada no nível"""
        colors = [
            "#7289DA",
            "#43B581",
            "#FAA61A",
            "#F04747",
            "#593695",
            "#FFD700",
        ]
        
        if level <= 10:
            return colors[0]
        elif level <= 25:
            return colors[1]
        elif level <= 50:
            return colors[2]
        elif level <= 75:
            return colors[3]
        elif level <= 100:
            return colors[4]
        else:
            return colors[5]
    
    def create_gradient(self, width: int, height: int, color1: tuple, color2: tuple) -> Image.Image:
        """Cria um gradiente entre duas cores"""
        base = Image.new('RGB', (width, height), color1)
        top = Image.new('RGB', (width, height), color2)
        
        mask = Image.new('L', (width, height))
        mask_data = []
        for y in range(height):
            for x in range(width):
                mask_data.append(int(255 * (y / height)))
        mask.putdata(mask_data)
        
        base.paste(top, (0, 0), mask)
        return base
    
    async def generate_profile_image(self, user_data: Dict, discord_user, rank: int = 1) -> io.BytesIO:
        """Gera a imagem do profile"""
        main_color = self.hex_to_rgb(user_data.get('favorite_color', '#7289DA'))
        level_color = self.hex_to_rgb(self.get_level_color(user_data['level']))
        
        banner_height = 220
        banner_url = user_data.get('banner_url')
        
        if banner_url:
            banner = self.load_image(banner_url)
            if banner:
                original_width, original_height = banner.size
                aspect_ratio = original_height / original_width
                ideal_height = int(self.base_width * aspect_ratio)
                
                ideal_height = max(1, ideal_height)
                
                max_safe_height = self.max_banner_height * 4
                
                if ideal_height > max_safe_height:
                    target_aspect = self.max_banner_height / self.base_width
                    crop_height = int(original_width * target_aspect)
                    crop_height = min(original_height, max(1, crop_height))
                    crop_y = max(0, (original_height - crop_height) // 2)
                    banner = banner.crop((0, crop_y, original_width, crop_y + crop_height))
                    banner = banner.resize((self.base_width, self.max_banner_height), Image.Resampling.LANCZOS)
                    banner_height = self.max_banner_height
                    
                elif ideal_height > self.max_banner_height:
                    banner = banner.resize((self.base_width, ideal_height), Image.Resampling.LANCZOS)
                    banner_height = self.max_banner_height
                    crop_y = (ideal_height - banner_height) // 2
                    banner = banner.crop((0, crop_y, self.base_width, crop_y + banner_height))
                    
                elif ideal_height < self.min_banner_height:
                    banner = banner.resize((self.base_width, ideal_height), Image.Resampling.LANCZOS)
                    banner_height = self.min_banner_height
                    letterbox_canvas = Image.new('RGB', (self.base_width, banner_height), (20, 20, 30))
                    paste_y = (banner_height - ideal_height) // 2
                    letterbox_canvas.paste(banner, (0, paste_y))
                    banner = letterbox_canvas
                    
                else:
                    banner = banner.resize((self.base_width, ideal_height), Image.Resampling.LANCZOS)
                    banner_height = ideal_height
                
                banner = banner.filter(ImageFilter.GaussianBlur(1))
                overlay = Image.new('RGBA', banner.size, (0, 0, 0, 100))
                banner = Image.alpha_composite(banner.convert('RGBA'), overlay).convert('RGB')
            else:
                banner = self.create_gradient(self.base_width, banner_height, main_color, (20, 20, 30))
        else:
            banner = self.create_gradient(self.base_width, banner_height, main_color, (20, 20, 30))
        
        total_height = banner_height + 210
        
        img = Image.new('RGB', (self.base_width, total_height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        img.paste(banner, (0, 0))
        
        card_start_y = banner_height - 30
        card_color = (40, 43, 48)
        draw.rounded_rectangle([0, card_start_y, self.base_width, total_height], 20, fill=card_color)
        
        avatar_url = str(discord_user.avatar.url) if discord_user.avatar else str(discord_user.default_avatar.url)
        avatar = self.download_image(avatar_url)
        if avatar:
            avatar = avatar.resize((self.avatar_size, self.avatar_size), Image.Resampling.LANCZOS)
            
            mask = Image.new('L', (self.avatar_size, self.avatar_size), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse([0, 0, self.avatar_size, self.avatar_size], fill=255)
            
            border_size = 6
            border_img = Image.new('RGBA', (self.avatar_size + border_size*2, self.avatar_size + border_size*2), level_color)
            border_mask = Image.new('L', border_img.size, 0)
            border_draw = ImageDraw.Draw(border_mask)
            border_draw.ellipse([0, 0, border_img.size[0], border_img.size[1]], fill=255)
            
            avatar_x = 50
            avatar_y = banner_height - 60
            
            img.paste(border_img, (avatar_x - border_size, avatar_y - border_size), border_mask)
            img.paste(avatar, (avatar_x, avatar_y), mask)
        
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
            font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        text_start_y = banner_height + 20
        
        name = discord_user.display_name
        if len(name) > 20:
            name = name[:17] + "..."
        
        draw.text((200, text_start_y), name, fill=(255, 255, 255), font=font_large)
        
        level_text = f"Nível {user_data['level']}"
        draw.text((200, text_start_y + 40), level_text, fill=level_color, font=font_medium)
        
        rank_text = f"#{rank} no servidor"
        draw.text((200, text_start_y + 65), rank_text, fill=(150, 150, 150), font=font_small)
        
        current_xp = user_data['xp']
        current_level = user_data['level']
        xp_for_current = ((current_level - 1) ** 2) * 100
        xp_for_next = (current_level ** 2) * 100
        xp_in_level = current_xp - xp_for_current
        xp_needed = xp_for_next - xp_for_current
        
        if xp_needed > 0:
            progress = xp_in_level / xp_needed
        else:
            progress = 1.0
        
        bar_width = 300
        bar_height = 20
        bar_x = 200
        bar_y = text_start_y + 100
        
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], 10, fill=(70, 70, 70))
        
        progress_width = int(bar_width * progress)
        if progress_width > 0:
            draw.rounded_rectangle([bar_x, bar_y, bar_x + progress_width, bar_y + bar_height], 10, fill=level_color)
        
        xp_text = f"{xp_in_level:,} / {xp_needed:,} XP"
        draw.text((bar_x, bar_y + 25), xp_text, fill=(200, 200, 200), font=font_small)
        
        stats_y = text_start_y + 150
        draw.text((50, stats_y), f"📊 XP Total: {current_xp:,}", fill=(200, 200, 200), font=font_small)
        draw.text((250, stats_y), f"💬 Mensagens: {user_data['messages_sent']:,}", fill=(200, 200, 200), font=font_small)
        
        bio = user_data.get('bio')
        if bio:
            bio_text = bio[:100] + "..." if len(bio) > 100 else bio
            draw.text((50, stats_y + 25), f"📝 {bio_text}", fill=(180, 180, 180), font=font_small)
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG', quality=95)
        img_byte_arr.seek(0)
        
        return img_byte_arr

image_gen = ProfileImageGenerator()
