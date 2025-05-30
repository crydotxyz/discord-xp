import aiohttp
import asyncio
import logging
import os
from colorama import Fore, Style, init
from datetime import datetime
from pyfiglet import Figlet
from tabulate import tabulate

# Initialize colorama for Windows Command Prompt
init(autoreset=True)

# Configure logging
logging.basicConfig(
    filename="monitor_activity.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def load_proxies():
    """Load proxies from proxy.txt file."""
    if not os.path.exists("proxy.txt"):
        return []
    with open("proxy.txt", "r") as f:
        return [line.strip() for line in f if line.strip()]

def format_proxy(proxy):
    """Format proxy string to aiohttp proxy format."""
    if not proxy:
        return None
    if proxy.count(":") == 3:  # username:password@host:port
        auth, host = proxy.rsplit("@", 1)
        return f"http://{auth}@{host}"
    elif proxy.count(":") == 1:  # host:port
        return f"http://{proxy}"
    return None

def log_message(nama_token, level, message):
    """Log message to file and console with colorful format and token prefix"""
    color_map = {"info": Fore.GREEN, "warning": Fore.YELLOW, "error": Fore.RED}
    color = color_map.get(level, Style.RESET_ALL)
    formatted_message = f"[{nama_token}] {message}"
    logging.log(getattr(logging, level.upper()), formatted_message)
    print(f"{color}{formatted_message}{Style.RESET_ALL}")

async def create_client_session(proxy=None):
    """Create aiohttp client session with optional proxy."""
    if proxy:
        return aiohttp.ClientSession(proxy=format_proxy(proxy))
    return aiohttp.ClientSession()

async def check_token_validity(session, nama_token, token):
    """Check if token is valid by making a request to Discord API."""
    headers = {"Authorization": token}
    url = "https://discord.com/api/v9/users/@me"
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                log_message(nama_token, "info", "✅ Token valid")
                return True
            elif response.status == 401:
                log_message(nama_token, "error", "❌ Token tidak valid")
                return False
            elif response.status == 429:
                retry_after = float(response.headers.get("Retry-After", 5))
                log_message(nama_token, "warning", f"⏳ Rate limit saat cek token, menunggu {retry_after} detik")
                await asyncio.sleep(retry_after)
                return await check_token_validity(session, nama_token, token)
            else:
                log_message(nama_token, "error", f"❌ Token error (Status: {response.status})")
                return False
    except Exception as e:
        log_message(nama_token, "error", f"❌ Error saat cek token: {str(e)}")
        return False

async def check_server_membership(session, nama_token, token, guild_id):
    """Check if token is still a member of the specified server."""
    headers = {"Authorization": token}
    member_url = f"https://discord.com/api/v9/guilds/{guild_id}/members/@me"
    
    try:
        # First check if token is still valid
        if not await check_token_validity(session, nama_token, token):
            log_message(nama_token, "error", "❌ Token tidak valid saat cek server membership")
            return {"valid": False, "in_server": False}

        async with session.get(member_url, headers=headers) as response:
            if response.status == 200:
                log_message(nama_token, "info", "✅ Masih ada di server")
                return {"valid": True, "in_server": True}
            elif response.status == 404:
                log_message(nama_token, "warning", "⚠️ Tidak ada di server (Banned/Kicked)")
                return {"valid": True, "in_server": False}
            elif response.status == 401:
                log_message(nama_token, "error", "❌ Token tidak valid saat cek server")
                return {"valid": False, "in_server": False}
            elif response.status == 429:
                retry_after = float(response.headers.get("Retry-After", 5))
                log_message(nama_token, "warning", f"⏳ Rate limit, menunggu {retry_after} detik")
                await asyncio.sleep(retry_after)
                return await check_server_membership(session, nama_token, token, guild_id)
            else:
                # Coba cek dengan endpoint guilds sebagai fallback
                guilds_url = "https://discord.com/api/v9/users/@me/guilds"
                async with session.get(guilds_url, headers=headers) as guilds_response:
                    if guilds_response.status == 200:
                        guilds = await guilds_response.json()
                        is_member = any(str(guild['id']) == str(guild_id) for guild in guilds)
                        if is_member:
                            log_message(nama_token, "info", "✅ Masih ada di server")
                            return {"valid": True, "in_server": True}
                    
                    log_message(nama_token, "warning", "⚠️ Tidak ada di server")
                    return {"valid": True, "in_server": False}
    except Exception as e:
        log_message(nama_token, "error", f"❌ Error saat cek membership: {str(e)}")
        return {"valid": True, "in_server": False}

async def validate_tokens(tokens, proxies):
    """Validate all tokens before proceeding."""
    valid_tokens = []
    invalid_tokens = []
    print(f"{Fore.YELLOW}--- Validasi Token ---{Style.RESET_ALL}")
    
    validation_results = []
    for i, (nama_token, token) in enumerate(tokens):
        proxy = proxies[i % len(proxies)] if proxies else None
        if proxy:
            log_message(nama_token, "info", f"🌐 Menggunakan proxy: {proxy}")
        async with await create_client_session(proxy) as session:
            is_valid = await check_token_validity(session, nama_token, token)
            validation_results.append([
                f"{Fore.CYAN}{nama_token}{Style.RESET_ALL}",
                f"{Fore.GREEN}Valid{Style.RESET_ALL}" if is_valid else f"{Fore.RED}Tidak Valid{Style.RESET_ALL}"
            ])
            if is_valid:
                valid_tokens.append((nama_token, token))
            else:
                invalid_tokens.append((nama_token, token))
    
    print("\n" + tabulate(validation_results, headers=[
        f"{Fore.YELLOW}Token{Style.RESET_ALL}",
        f"{Fore.YELLOW}Status{Style.RESET_ALL}"
    ], tablefmt="grid"))
    
    # Continue with all tokens
    all_tokens = valid_tokens + invalid_tokens

    return all_tokens

async def leave_server(session, guild_id, nama_token, token):
    """Leave a Discord server using the token."""
    headers = {"Authorization": token}
    url = f"https://discord.com/api/v9/users/@me/guilds/{guild_id}"
    try:
        async with session.delete(url, headers=headers) as response:
            if response.status == 204:
                log_message(nama_token, "info", f"🚪 Berhasil keluar dari server {guild_id}")
                return True
            elif response.status == 404:
                log_message(nama_token, "info", f"ℹ️ Sudah tidak ada di server {guild_id}")
                return True
            elif response.status == 429:
                retry_after = float(response.headers.get("Retry-After", 5))
                log_message(nama_token, "warning", f"⏳ Rate limit saat leave server, menunggu {retry_after} detik")
                await asyncio.sleep(retry_after)
                return await leave_server(session, guild_id, nama_token, token)
            else:
                log_message(nama_token, "error", f"❌ Gagal keluar dari server (Status: {response.status})")
                return False
    except Exception as e:
        log_message(nama_token, "error", f"❌ Error saat leave server: {str(e)}")
        return False

async def monitor_token(session, nama_token, token, guild_id, all_tokens, monitoring_active, initial_status, start_time):
    """Monitor a single token's status continuously."""
    check_interval = 10  # Check every 10 seconds
    
    # Skip monitoring if token wasn't in server initially
    if not initial_status.get(nama_token, {}).get("in_server", False):
        log_message(nama_token, "info", "🔍 Token tidak dimonitor karena tidak ada di server sejak awal")
        return
    
    last_status = initial_status.get(nama_token, {})
    status_messages = {}  # Untuk menyimpan pesan status terakhir setiap token
    exit_success = {}  # Untuk melacak token yang berhasil keluar
    
    def clear_console():
        """Clear console screen."""
        print("\033[H\033[J", end="")  # ANSI escape sequence untuk clear screen
    
    def get_running_time():
        """Get formatted running time."""
        running_time = datetime.now() - start_time
        hours, remainder = divmod(running_time.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def print_monitor_header():
        """Print monitor header with running time."""
        running_time = get_running_time()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{Fore.CYAN}╔{'═' * 50}╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║{Style.RESET_ALL} 🔍 DISCORD TOKEN MONITOR {' ' * 30}║")
        print(f"{Fore.CYAN}║{Style.RESET_ALL} ⏱️ Running Time: {running_time}{' ' * (35 - len(running_time))}║")
        print(f"{Fore.CYAN}║{Style.RESET_ALL} ⏰ {current_time}{' ' * (44 - len(current_time))}║")
        print(f"{Fore.CYAN}╠{'═' * 50}╣{Style.RESET_ALL}")
    
    def get_status_text(token_status, is_forced_leave=False, has_exited=False):
        """Get formatted status text based on token status."""
        if has_exited:
            return f"{Fore.GREEN}Berhasil Keluar{Style.RESET_ALL}"
        if not token_status.get("valid", True):
            return f"{Fore.RED}Tidak Valid{Style.RESET_ALL}"
        elif not token_status.get("in_server", False):
            if is_forced_leave:
                return f"{Fore.YELLOW}Proses Keluar{Style.RESET_ALL}"
            else:
                return f"{Fore.RED}Tidak di server{Style.RESET_ALL}"
        return f"{Fore.GREEN}Di Server{Style.RESET_ALL}"
    
    while monitoring_active[0]:
        status = await check_server_membership(session, nama_token, token, guild_id)
        
        # Jika status berubah dari sebelumnya
        if status != last_status:
            if not status["valid"]:
                log_message(nama_token, "error", "🚨 Token tidak valid!")
                status_messages[nama_token] = "Token tidak valid"
            elif not status["in_server"] and last_status.get("in_server", False):
                log_message(nama_token, "error", "🚨 Token terdeteksi di-ban/kick dari server!")
                status_messages[nama_token] = "Banned/Kicked dari server"
                log_message(nama_token, "info", "🔄 Mengeluarkan semua token dari server...")
                
                # Create tasks for all tokens to leave the server
                leave_tasks = []
                for other_nama, other_token in all_tokens:
                    if other_nama != nama_token and initial_status.get(other_nama, {}).get("in_server", False):
                        leave_task = leave_server(session, guild_id, other_nama, other_token)
                        leave_tasks.append(leave_task)
                        status_messages[other_nama] = "Proses keluar dari server"
                
                if leave_tasks:
                    results = await asyncio.gather(*leave_tasks, return_exceptions=True)
                    for i, result in enumerate(results):
                        other_nama = [n for n, _ in all_tokens][i]
                        if isinstance(result, bool) and result:
                            exit_success[other_nama] = True
                            status_messages[other_nama] = "Berhasil keluar dari server"
                        else:
                            status_messages[other_nama] = "Gagal keluar dari server"
                
                monitoring_active[0] = False
                break
            
            last_status = status
        
        # Tampilkan status monitor yang lebih rapi
        clear_console()
        print_monitor_header()
        
        # Tampilkan status semua token
        status_display = []
        for other_nama, other_token in all_tokens:
            if other_nama == nama_token:
                token_status = status
                is_forced = False
            else:
                token_status = initial_status.get(other_nama, {})
                is_forced = status_messages.get(other_nama, "").startswith("Proses")
            
            has_exited = exit_success.get(other_nama, False)
            status_text = get_status_text(token_status, is_forced, has_exited)
            message = status_messages.get(other_nama, "")
            status_display.append([
                f"{Fore.CYAN}{other_nama}{Style.RESET_ALL}",
                status_text,
                f"{Fore.YELLOW}{message}{Style.RESET_ALL}" if message else ""
            ])
        
        print(tabulate(status_display, headers=[
            f"{Fore.YELLOW}Token{Style.RESET_ALL}",
            f"{Fore.YELLOW}Status{Style.RESET_ALL}",
            f"{Fore.YELLOW}Keterangan{Style.RESET_ALL}"
        ], tablefmt="grid"))
        
        # Footer
        print(f"{Fore.CYAN}╠{'═' * 50}╣{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║{Style.RESET_ALL} Press Ctrl+C to stop monitoring{' ' * 26}║")
        print(f"{Fore.CYAN}╚{'═' * 50}╝{Style.RESET_ALL}")
        
        await asyncio.sleep(check_interval)
    
    return exit_success

async def main():
    # Display banner
    f = Figlet(font='slant')
    print(f"{Fore.CYAN}{f.renderText('TOKEN MONITOR')}{Style.RESET_ALL}")
    
    print(f"{Fore.CYAN}=== Token Monitor System ==={Style.RESET_ALL}")
    
    try:
        # Load tokens and proxies
        with open("token.txt", "r") as f:
            tokens = [line.strip().split(":") for line in f.readlines() if ":" in line]
        
        if not tokens:
            raise ValueError("⚠️ File token.txt kosong!")
        
        proxies = load_proxies()
        if proxies:
            print(f"{Fore.CYAN}ℹ️ Loaded {len(proxies)} proxies{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}⚠️ No proxies found in proxy.txt, running without proxies{Style.RESET_ALL}")
        
        # Validate tokens first but continue with all tokens
        all_tokens = await validate_tokens(tokens, proxies)
        if not all_tokens:
            print(f"{Fore.RED}❌ Tidak ada token yang valid untuk dimonitor.{Style.RESET_ALL}")
            return
        
        # Get server ID
        guild_id = input(f"{Fore.CYAN}🔹 Masukkan ID Server yang akan dimonitor: {Style.RESET_ALL}").strip()
        if not guild_id or not guild_id.isdigit():
            raise ValueError("⚠️ Server ID harus angka dan tidak boleh kosong!")
        
        print(f"{Fore.YELLOW}--- Memulai Monitoring Token ---{Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}🔍 Monitoring {len(all_tokens)} token...{Style.RESET_ALL}")
        
        monitoring_active = [True]
        initial_status = {}
        start_time = datetime.now()
        
        # Create sessions for each token with their respective proxies
        sessions = []
        for i, (nama_token, token) in enumerate(all_tokens):
            proxy = proxies[i % len(proxies)] if proxies else None
            if proxy:
                log_message(nama_token, "info", f"🌐 Menggunakan proxy: {proxy}")
            session = await create_client_session(proxy)
            sessions.append((session, nama_token, token))
        
        try:
            # Check initial status
            print(f"{Fore.YELLOW}--- Mengecek Status Awal Token ---{Style.RESET_ALL}")
            initial_status_display = []
            
            for session, nama_token, token in sessions:
                status = await check_server_membership(session, nama_token, token, guild_id)
                initial_status[nama_token] = status
                status_text = (f"{Fore.GREEN}Di Server{Style.RESET_ALL}" if status["in_server"] else 
                             f"{Fore.RED}Tidak Valid{Style.RESET_ALL}" if not status["valid"] else 
                             f"{Fore.YELLOW}Tidak Di Server{Style.RESET_ALL}")
                initial_status_display.append([f"{Fore.CYAN}{nama_token}{Style.RESET_ALL}", status_text])
            
            print(tabulate(initial_status_display, headers=[
                f"{Fore.YELLOW}Token{Style.RESET_ALL}",
                f"{Fore.YELLOW}Status{Style.RESET_ALL}"
            ], tablefmt="grid"))
            
            # Create monitoring tasks
            monitor_tasks = [
                monitor_token(session, nama_token, token, guild_id, all_tokens, monitoring_active, initial_status, start_time)
                for session, nama_token, token in sessions
            ]
            
            # Start monitoring
            exit_results = await asyncio.gather(*monitor_tasks)
            all_exit_success = {k: v for d in exit_results if d for k, v in d.items()}
            
        except KeyboardInterrupt:
            monitoring_active[0] = False
            print(f"{Fore.YELLOW}⏹️ Monitoring dihentikan oleh pengguna{Style.RESET_ALL}")
        except Exception as e:
            monitoring_active[0] = False
            print(f"{Fore.RED}🚨 Error: {str(e)}{Style.RESET_ALL}")
        finally:
            # Close all sessions
            for session, _, _ in sessions:
                await session.close()
            
            # Final status display with running time
            end_time = datetime.now()
            running_time = end_time - start_time
            hours, remainder = divmod(running_time.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{Fore.CYAN}╔{'═' * 50}╗{Style.RESET_ALL}")
            print(f"{Fore.CYAN}║{Style.RESET_ALL} 📊 STATUS AKHIR TOKEN {' ' * 32}║")
            print(f"{Fore.CYAN}║{Style.RESET_ALL} ⏱️ Total Waktu: {hours:02d}:{minutes:02d}:{seconds:02d}{' ' * 31}║")
            print(f"{Fore.CYAN}║{Style.RESET_ALL} ⏰ {current_time}{' ' * (44 - len(current_time))}║")
            print(f"{Fore.CYAN}╠{'═' * 50}╣{Style.RESET_ALL}")
            
            def get_final_status_text(status, has_exited=False):
                """Get formatted status text for final display."""
                if has_exited:
                    return f"{Fore.GREEN}Keluar{Style.RESET_ALL}"
                if not status.get("valid", True):
                    return f"{Fore.RED}Tidak Valid{Style.RESET_ALL}"
                elif not status.get("in_server", False):
                    return f"{Fore.RED}Banned/Kicked{Style.RESET_ALL}"
                return f"{Fore.GREEN}Di Server{Style.RESET_ALL}"
            
            final_status = []
            async with aiohttp.ClientSession() as session:
                for nama_token, token in all_tokens:
                    status = await check_server_membership(session, nama_token, token, guild_id)
                    status_text = get_final_status_text(status, all_exit_success.get(nama_token, False))
                    final_status.append([
                        f"{Fore.CYAN}{nama_token}{Style.RESET_ALL}",
                        status_text,
                        f"{Fore.GREEN}✓ Berhasil Keluar{Style.RESET_ALL}" if all_exit_success.get(nama_token, False) else ""
                    ])
            
            print(tabulate(final_status, headers=[
                f"{Fore.YELLOW}Token{Style.RESET_ALL}",
                f"{Fore.YELLOW}Status Akhir{Style.RESET_ALL}",
                f"{Fore.YELLOW}Hasil{Style.RESET_ALL}"
            ], tablefmt="grid"))
            print(f"{Fore.CYAN}╚{'═' * 50}╝{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}🚨 Error: {str(e)}{Style.RESET_ALL}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"{Fore.YELLOW}🏁 Monitor dihentikan oleh pengguna.{Style.RESET_ALL}") 
