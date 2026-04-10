import json
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.logging import RichHandler
from rich.rule import Rule
from rich import box

# --- 配置与常量 ---
LOG_FILE = Path("rename_history.log")
WHITELIST_FILE = Path("whitelist.json")
SYSTEM_VOLUMES_BLACKLIST = {'Macintosh HD', 'Preboot', 'Recovery', 'VM', 'Update'}

# 初始化 Rich Console
console = Console()

# 设置日志，强制覆盖旧配置并确保 handlers 正确加载
def setup_logging():
    # 强制清理旧的 handlers (防止在某些环境下重复或失效)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="[%Y-%m-%d %X]",
        handlers=[
            logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
            RichHandler(console=console, rich_tracebacks=True, show_path=False)
        ],
        force=True # 强制覆盖任何现有的日志配置
    )

@dataclass(frozen=True)
class VolumeInfo:
    """卷信息数据类"""
    name: str
    path: Path
    device_id: Optional[str]

    def __str__(self):
        return f"{self.name} ([dim]{self.path}[/dim])"

class WhitelistManager:
    """白名单管理器"""
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.whitelist: Dict[str, str] = {} # {device_id: name}
        self.load()

    def load(self):
        if self.file_path.exists():
            try:
                self.whitelist = json.loads(self.file_path.read_text())
            except (json.JSONDecodeError, Exception) as e:
                logging.error(f"Failed to load whitelist: {e}")

    def save(self):
        try:
            self.file_path.write_text(json.dumps(self.whitelist, indent=4))
        except Exception as e:
            logging.error(f"Failed to save whitelist: {e}")

    def add(self, vol: VolumeInfo):
        if vol.device_id:
            self.whitelist[vol.device_id] = vol.name
            self.save()

    def remove(self, device_id: str):
        if device_id in self.whitelist:
            del self.whitelist[device_id]
            self.save()

    def clear(self):
        self.whitelist.clear()
        self.save()

    def contains(self, device_id: Optional[str]) -> bool:
        return device_id in self.whitelist if device_id else False

class VolumeRenamer:
    """核心重命名管线"""
    def __init__(self, whitelist_mgr: WhitelistManager):
        self.whitelist_mgr = whitelist_mgr

    def get_external_volumes(self, include_whitelisted: bool = False) -> List[VolumeInfo]:
        """获取外部卷列表"""
        volumes = []
        volumes_root = Path('/Volumes')
        if not volumes_root.exists():
            return []

        for item in volumes_root.iterdir():
            if item.name.startswith('.') or item.name in SYSTEM_VOLUMES_BLACKLIST:
                continue
            
            if item.is_mount():
                try:
                    result = subprocess.run(['diskutil', 'info', str(item)], capture_output=True, text=True, check=True)
                    output = result.stdout
                    
                    is_external = any(k in output for k in ["External", "USB", "FireWire", "Thunderbolt"])
                    if is_external:
                        device_id = None
                        if match := re.search(r'Device Identifier:\s+(\w+)', output):
                            device_id = match.group(1)
                        
                        if not include_whitelisted and self.whitelist_mgr.contains(device_id):
                            continue
                            
                        volumes.append(VolumeInfo(name=item.name, path=item, device_id=device_id))
                except subprocess.CalledProcessError:
                    continue
        return volumes

    def rename(self, vol: VolumeInfo, new_name: str) -> bool:
        """执行重命名并刷新挂载"""
        console.print(f"[bold blue]Renaming[/bold blue] '{vol.name}' -> [bold green]'{new_name}'[/bold green]")
        try:
            subprocess.run(['diskutil', 'rename', str(vol.path), new_name], check=True, capture_output=True)
            if vol.device_id:
                console.print(f"[dim]Refreshing mount for {vol.device_id}...[/dim]")
                subprocess.run(['diskutil', 'unmount', vol.device_id], check=True, capture_output=True)
                subprocess.run(['diskutil', 'mount', vol.device_id], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Rename failed for {vol.name}: {e.stderr.decode().strip()}")
            return False

    @staticmethod
    def get_extension_examples(path: Path) -> Dict[str, str]:
        """扫描文件示例"""
        examples = {}
        try:
            for file in path.rglob('*'):
                if file.is_file() and not file.name.startswith('.'):
                    ext = file.suffix.lower()
                    if ext and ext not in examples:
                        examples[ext] = file.name
        except Exception:
            pass
        return examples

    @staticmethod
    def extract_name(path: Path, ext: str, pos: str, length: int) -> Optional[str]:
        """按规则提取文件名 (支持大小写不敏感匹配)"""
        target_ext = ext if ext.startswith('.') else f".{ext}"
        target_ext = target_ext.lower()
        try:
            # 使用与 get_extension_examples 相同的遍历逻辑，确保匹配的一致性
            for file in path.rglob('*'):
                if file.is_file() and not file.name.startswith('.'):
                    if file.suffix.lower() == target_ext:
                        stem = file.stem
                        return stem[:length] if pos == '1' else stem[-length:]
        except Exception as e:
            logging.debug(f"Extraction error in {path}: {e}")
        return None

class CLIHandler:
    """交互逻辑处理器 (基于 Rich)"""
    def __init__(self, renamer: VolumeRenamer):
        self.renamer = renamer

    def show_title(self, title: str):
        console.print(Rule(title, style="magenta"))

    def parse_selection(self, input_str: str, max_count: int) -> List[int]:
        if input_str.lower() == 'all':
            return list(range(max_count))
        
        indices = set()
        for part in input_str.replace(',', ' ').split():
            if '-' in part:
                try:
                    s, e = map(int, part.split('-'))
                    indices.update(range(s-1, e))
                except ValueError: continue
            else:
                try:
                    indices.add(int(part)-1)
                except ValueError: continue
        return [i for i in sorted(indices) if 0 <= i < max_count]

    def manage_whitelist(self):
        while True:
            self.show_title("Whitelist Management")
            console.print("1. View Current Whitelist\n2. Add Current Volumes\n3. Remove Items\n4. Reset All\n0. Back")
            choice = Prompt.ask("Select", choices=["1", "2", "3", "4", "0"], default="0")
            
            if choice == '0': break
            
            if choice == '1':
                self.show_title("Current Persistent Whitelist")
                if not self.renamer.whitelist_mgr.whitelist:
                    console.print("[yellow]Whitelist is empty.[/yellow]")
                else:
                    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
                    table.add_column("Device ID", style="dim")
                    table.add_column("Original Name")
                    for d_id, name in self.renamer.whitelist_mgr.whitelist.items():
                        table.add_row(d_id, name)
                    console.print(table)
            
            elif choice == '2':
                vols = self.renamer.get_external_volumes(include_whitelisted=True)
                if not vols:
                    console.print("[yellow]No external volumes found.[/yellow]")
                    continue
                
                table = Table(title="Available Volumes", box=box.SIMPLE)
                table.add_column("No.", justify="right", style="cyan")
                table.add_column("Name")
                table.add_column("Device ID", style="dim")
                table.add_column("Status")
                
                for i, v in enumerate(vols):
                    status = "[bold yellow]Whitelisted[/bold yellow]" if self.renamer.whitelist_mgr.contains(v.device_id) else ""
                    table.add_row(str(i+1), v.name, v.device_id or "N/A", status)
                console.print(table)

                sel = Prompt.ask("\nEnter numbers to add (e.g. 1, 1-2, all, 0 to cancel)")
                if sel == '0': continue
                for i in self.parse_selection(sel, len(vols)):
                    self.renamer.whitelist_mgr.add(vols[i])
                    console.print(f"[green]Added[/green] '{vols[i].name}' to whitelist.")

            elif choice == '3':
                items = list(self.renamer.whitelist_mgr.whitelist.items())
                if not items:
                    console.print("[yellow]Whitelist is already empty.[/yellow]")
                    continue
                
                table = Table(title="Items in Whitelist", box=box.SIMPLE)
                table.add_column("No.", justify="right", style="cyan")
                table.add_column("Name")
                table.add_column("Device ID", style="dim")
                for i, (d_id, name) in enumerate(items):
                    table.add_row(str(i+1), name, d_id)
                console.print(table)

                sel = Prompt.ask("\nEnter numbers to remove")
                for i in self.parse_selection(sel, len(items)):
                    d_id, name = items[i]
                    self.renamer.whitelist_mgr.remove(d_id)
                    console.print(f"[red]Removed[/red] '{name}' from whitelist.")

            elif choice == '4':
                if Confirm.ask("Reset entire whitelist?"):
                    self.renamer.whitelist_mgr.clear()
                    console.print("[bold red]Whitelist cleared.[/bold red]")

    def run_rename_pipeline(self, volumes: List[VolumeInfo]):
        if not volumes:
            console.print("[yellow]No volumes to process.[/yellow]")
            return
        
        targets = volumes
        if len(volumes) > 1:
            self.show_title("Detected Volumes")
            table = Table(box=box.SIMPLE)
            table.add_column("No.", justify="right", style="cyan")
            table.add_column("Volume Info")
            for i, v in enumerate(volumes):
                table.add_row(str(i+1), str(v))
            console.print(table)

            sel = Prompt.ask("\nSelect targets (e.g. 1, 1-2, all, 0 to cancel)")
            if sel == '0': return
            indices = self.parse_selection(sel, len(volumes))
            targets = [volumes[i] for i in indices]
        
        if not targets: return

        while True:
            self.show_title(f"Processing {len(targets)} Volumes")
            for i, v in enumerate(targets):
                console.print(f"  {i+1}. [bold cyan]{v.name}[/bold cyan] ([dim]{v.device_id}[/dim])")
            
            console.print("\nRules:\n1. Auto-increment (CARD#1, CARD#2...)\n2. Extract from filename\n0. Back")
            rule = Prompt.ask("Choice", choices=["1", "2", "0"], default="0")
            if rule == '0': return
            
            previews = []
            if rule == '1':
                prefix = Prompt.ask("Prefix", default="CARD#")
                start = IntPrompt.ask("Start number", default=1)
                previews = [(v, f"{prefix}{start+i}") for i, v in enumerate(targets)]
                break

            elif rule == '2':
                console.print("\n[bold yellow]Scanning all targets for file examples...[/bold yellow]")
                all_examples = {v.name: self.renamer.get_extension_examples(v.path) for v in targets}
                
                if not any(all_examples.values()):
                    console.print("[red]No files found in any selected volume.[/red]")
                    continue
                
                self.show_title("File Scan Results")
                for name, ex in all_examples.items():
                    table = Table(title=f"Volume: {name}", box=box.MINIMAL_DOUBLE_HEAD)
                    table.add_column("Extension", style="green")
                    table.add_column("Example File")
                    for ext, file in sorted(ex.items()):
                        table.add_row(ext, file)
                    console.print(table)
                
                console.print("\nSub-options:\n1. Extraction Rules (Prefix/Suffix)\n2. Manual Input\n0. Back")
                sub = Prompt.ask("Choice", choices=["1", "2", "0"], default="0")
                if sub == '0': continue
                
                if sub == '1':
                    ext = Prompt.ask("Enter extension to target (e.g. mp4, mov)").strip()
                    console.print("Extract from:\n1. Prefix (Start of name)\n2. Suffix (End of name)")
                    pos = Prompt.ask("Choice", choices=["1", "2"], default="1")
                    length = IntPrompt.ask("Number of characters to extract")
                    
                    for v in targets:
                        if name := self.renamer.extract_name(v.path, ext, pos, length):
                            previews.append((v, name))
                        else:
                            console.print(f"[bold red]Warning:[/bold red] No matching '{ext}' file in '{v.name}'")
                    break
                elif sub == '2':
                    for v in targets:
                        if name := Prompt.ask(f"New name for [bold cyan]{v.name}[/bold cyan]").strip():
                            previews.append((v, name))
                    break
        
        if previews:
            self.show_title("Final Preview")
            table = Table(show_header=True, header_style="bold green", box=box.ROUNDED)
            table.add_column("Original Volume")
            table.add_column("New Name", style="bold green")
            for v, n in previews:
                table.add_row(v.name, n)
            console.print(table)

            if Confirm.ask("\n[bold yellow]Proceed with these changes?[/bold yellow]"):
                for v, n in previews:
                    self.renamer.rename(v, n)

    def monitor_mode(self):
        console.print(Panel("[bold green]Real-time Monitoring Mode Started[/bold green]\nScanning for new volumes every 2 seconds...\n[dim]Press Ctrl+C to exit[/dim]", border_style="green"))
        
        known = {v.device_id for v in self.renamer.get_external_volumes() if v.device_id}
        try:
            while True:
                current = self.renamer.get_external_volumes()
                curr_ids = {v.device_id for v in current if v.device_id}
                new_ids = curr_ids - known
                
                if new_ids:
                    new_vols = [v for v in current if v.device_id in new_ids]
                    console.print(f"\n[bold yellow][!] Detected {len(new_vols)} new volume(s):[/bold yellow] {[v.name for v in new_vols]}")
                    self.run_rename_pipeline(new_vols)
                    # 重新扫描以确保 ID 列表是最新的
                    known = {v.device_id for v in self.renamer.get_external_volumes() if v.device_id}
                
                known &= curr_ids
                time.sleep(2)
        except KeyboardInterrupt:
            console.print("\n[bold red]Monitoring Mode Stopped.[/bold red]")

def main():
    # 确保日志文件存在
    if not LOG_FILE.exists():
        LOG_FILE.touch()
    
    # 初始化日志配置
    setup_logging()
        
    renamer = VolumeRenamer(WhitelistManager(WHITELIST_FILE))
    cli = CLIHandler(renamer)
    
    actions = {
        '1': lambda: cli.run_rename_pipeline(renamer.get_external_volumes()),
        '2': cli.monitor_mode,
        '3': cli.manage_whitelist,
        '4': lambda: console.print(Rule("History Log", style="cyan"), Panel(LOG_FILE.read_text() if LOG_FILE.stat().st_size > 0 else "[dim italic]No history recorded yet.[/dim italic]")) if LOG_FILE.exists() else console.print("[yellow]No log file found.[/yellow]")
    }

    while True:
        console.print(Panel.fit(
            "[bold cyan]Auto Batch Rename Volumes[/bold cyan]\n"
            "[dim]Pythonic Volume Management Tool[/dim]\n\n"
            "1. [bold]Scan & Rename[/bold] (Manual Scan)\n"
            "2. [bold]Monitoring[/bold] (Auto Detect)\n"
            "3. [bold]Whitelist[/bold] (Exclude Volumes)\n"
            "4. [bold]History[/bold] (View Logs)\n"
            "0. [bold red]Exit[/bold red]",
            box=box.DOUBLE
        ))
        
        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "0"], default="0")
        if choice == '0':
            console.print("[italic]Goodbye![/italic]")
            break
        
        try:
            actions.get(choice, lambda: None)()
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
