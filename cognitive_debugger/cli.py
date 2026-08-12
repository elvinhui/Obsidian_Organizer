"""
Rich CLI interface for the Cognitive Debugger.
Double-click debug_my_mind.bat to launch.
"""
import sys
import os

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.text import Text

from cognitive_debugger.bot import CognitiveDebuggerBot, TOTAL_ROUNDS
from cognitive_debugger.prompts import ROUND_LABELS, WELCOME_MESSAGE
from cognitive_debugger.session import archive_session

console = Console()

def run_cli():
    """Main CLI loop for the Cognitive Debugger."""
    console.print(Panel(
        Markdown(WELCOME_MESSAGE),
        title="🧠 认知调试器 Cognitive Debugger",
        border_style="cyan",
        expand=False
    ))
    
    # Get initial worry
    console.print()
    worry = Prompt.ask("[bold yellow]💭 你现在在烦恼什么？请描述你的困扰[/bold yellow]")
    
    if worry.lower() in ("exit", "quit", "q"):
        console.print("[dim]再见！记住：大部分焦虑都是你大脑编造的故事。[/dim]")
        return
    
    bot = CognitiveDebuggerBot()
    
    # Round 1: Start session
    console.print()
    console.print(Panel(
        f"[bold cyan]{ROUND_LABELS[0]}[/bold cyan]",
        border_style="blue"
    ))
    
    with console.status("[bold green]苏格拉底正在思考...[/bold green]"):
        reply = bot.start_session(worry)
    
    console.print(Panel(Markdown(reply), border_style="green", title="🏛️ 苏格拉底"))
    
    # Rounds 2-5
    for i in range(1, TOTAL_ROUNDS):
        console.print()
        user_input = Prompt.ask(f"[bold yellow]💬 你的回答 (第{i}轮)[/bold yellow]")
        
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]会话提前结束。[/dim]")
            return
        
        console.print()
        if i < TOTAL_ROUNDS - 1:
            console.print(Panel(
                f"[bold cyan]{ROUND_LABELS[i]}[/bold cyan]",
                border_style="blue"
            ))
        else:
            console.print(Panel(
                "[bold cyan]最终轮：生成认知调试报告...[/bold cyan]",
                border_style="magenta"
            ))
        
        with console.status("[bold green]苏格拉底正在深度分析...[/bold green]"):
            reply = bot.next_round(user_input)
        
        if bot.is_complete:
            console.print(Panel(
                Markdown(reply),
                border_style="magenta",
                title="📋 认知调试报告"
            ))
        else:
            console.print(Panel(Markdown(reply), border_style="green", title="🏛️ 苏格拉底"))
    
    # If we went through all rounds but report wasn't generated yet (user answered 5th round)
    if not bot.is_complete:
        user_input = Prompt.ask("[bold yellow]💬 你的最后回答[/bold yellow]")
        with console.status("[bold green]正在生成认知调试报告...[/bold green]"):
            reply = bot.next_round(user_input)
        console.print(Panel(
            Markdown(reply),
            border_style="magenta",
            title="📋 认知调试报告"
        ))
    
    # Archive to Obsidian
    console.print()
    with console.status("[bold blue]正在归档到 Obsidian...[/bold blue]"):
        dialogue_md = bot.get_full_dialogue_markdown()
        saved_path = archive_session(dialogue_md)
    
    if saved_path:
        console.print(Panel(
            f"[green]✅ 会话已归档至：[/green]\n[cyan]{saved_path}[/cyan]",
            border_style="green",
            title="📂 归档完成"
        ))
    
    console.print()
    console.print("[dim]记住：你不是你的想法。想法只是天空中飘过的云，你是那片天空。[/dim]")
    console.print()
    input("按 Enter 键退出...")

if __name__ == "__main__":
    run_cli()
