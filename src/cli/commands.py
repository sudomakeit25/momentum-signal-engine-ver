"""CLI commands for the Momentum Signal Engine."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from src.backtest.engine import run_backtest
from src.data import client
from src.data.models import SignalAction
from src.risk.position_sizer import calculate_position_size
from src.risk.rr_calculator import rate_setup
from src.scanner.screener import get_default_universe, scan_universe
from src.signals.generator import generate_signals
from src.signals.patterns import detect_patterns

app = typer.Typer(name="mse", help="Momentum Signal Engine — find high-probability setups")
console = Console()


@app.command()
def scan(
    top: int = typer.Option(20, "--top", "-n", help="Number of top results"),
    min_price: float = typer.Option(5.0, "--min-price", help="Minimum price"),
    max_price: float = typer.Option(500.0, "--max-price", help="Maximum price"),
    min_volume: int = typer.Option(500_000, "--min-volume", help="Minimum avg volume"),
):
    """Run momentum scanner on the default universe."""
    with console.status("Scanning for momentum stocks..."):
        symbols = get_default_universe()
        results = scan_universe(
            symbols, top_n=top, min_price=min_price, max_price=max_price, min_volume=min_volume
        )

    if not results:
        console.print("[yellow]No momentum stocks found matching criteria.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Top {len(results)} Momentum Stocks")
    table.add_column("Rank", justify="right", style="dim")
    table.add_column("Symbol", style="bold cyan")
    table.add_column("Price", justify="right")
    table.add_column("Change %", justify="right")
    table.add_column("Volume", justify="right")
    table.add_column("RS", justify="right")
    table.add_column("Score", justify="right", style="bold")
    table.add_column("Setups", style="green")

    for i, r in enumerate(results, 1):
        change_style = "green" if r.change_pct >= 0 else "red"
        score_style = "bold green" if r.score >= 60 else "bold yellow" if r.score >= 40 else "dim"
        table.add_row(
            str(i),
            r.symbol,
            f"${r.price:.2f}",
            f"[{change_style}]{r.change_pct:+.2f}%[/{change_style}]",
            f"{r.volume:,}",
            f"{r.relative_strength:.3f}",
            f"[{score_style}]{r.score:.1f}[/{score_style}]",
            ", ".join(s.value for s in r.setup_types) or "-",
        )

    console.print(table)


@app.command()
def analyze(symbol: str = typer.Argument(..., help="Stock symbol to analyze")):
    """Detailed analysis of a single stock."""
    symbol = symbol.upper()
    with console.status(f"Analyzing {symbol}..."):
        results = scan_universe([symbol], top_n=1)
        df = client.get_bars(symbol, days=200)
        signals = generate_signals(df, symbol)
        patterns = detect_patterns(df)

    if not results:
        console.print(f"[yellow]{symbol} did not pass momentum filters.[/yellow]")
    else:
        r = results[0]
        console.print(f"\n[bold cyan]{symbol}[/bold cyan] — Momentum Score: [bold]{r.score:.1f}/100[/bold]")
        console.print(f"  Price: ${r.price:.2f}  |  Change: {r.change_pct:+.2f}%  |  RS: {r.relative_strength:.3f}")
        console.print(f"  Volume: {r.volume:,}  |  Avg Volume: {r.avg_volume:,}")

    if patterns:
        console.print(f"\n[bold]Patterns:[/bold] {', '.join(p.value for p in patterns)}")

    if signals:
        console.print(f"\n[bold]Signals ({len(signals)}):[/bold]")
        for s in signals:
            icon = "[green]BUY[/green]" if s.action == SignalAction.BUY else "[red]SELL[/red]"
            rating = rate_setup(s.rr_ratio) if s.action == SignalAction.BUY else ""
            console.print(
                f"  {icon} {s.setup_type.value} — "
                f"Entry: ${s.entry:.2f}  Stop: ${s.stop_loss:.2f}  "
                f"Target: ${s.target:.2f}  R:R {s.rr_ratio:.1f}:1 "
                f"({rating}) Confidence: {s.confidence:.0%}"
            )
            if s.reason:
                console.print(f"    [dim]{s.reason}[/dim]")
    else:
        console.print("\n[dim]No active signals.[/dim]")


@app.command()
def signals(
    symbol: Optional[str] = typer.Argument(None, help="Optional: specific symbol"),
    top: int = typer.Option(20, "--top", "-n", help="Number of signals to show"),
):
    """Show current buy/sell signals."""
    if symbol:
        symbol = symbol.upper()
        with console.status(f"Generating signals for {symbol}..."):
            df = client.get_bars(symbol, days=200)
            sigs = generate_signals(df, symbol)
    else:
        with console.status("Scanning for signals..."):
            universe = get_default_universe()
            bars_map = client.get_multi_bars(universe, days=200)
            sigs = []
            for sym, df in bars_map.items():
                if len(df) >= 50:
                    try:
                        sigs.extend(generate_signals(df, sym))
                    except Exception:
                        continue
            sigs.sort(key=lambda s: s.confidence, reverse=True)
            sigs = sigs[:top]

    if not sigs:
        console.print("[yellow]No signals found.[/yellow]")
        raise typer.Exit()

    table = Table(title="Active Signals")
    table.add_column("Symbol", style="bold cyan")
    table.add_column("Action", justify="center")
    table.add_column("Setup", style="dim")
    table.add_column("Entry", justify="right")
    table.add_column("Stop", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("R:R", justify="right")
    table.add_column("Rating", justify="center")
    table.add_column("Conf", justify="right")
    table.add_column("Reason", style="dim", max_width=50)

    for s in sigs:
        action_style = "[green]BUY[/green]" if s.action == SignalAction.BUY else "[red]SELL[/red]"
        rating = rate_setup(s.rr_ratio) if s.action == SignalAction.BUY else "-"
        table.add_row(
            s.symbol,
            action_style,
            s.setup_type.value,
            f"${s.entry:.2f}",
            f"${s.stop_loss:.2f}" if s.stop_loss > 0 else "-",
            f"${s.target:.2f}" if s.target > 0 else "-",
            f"{s.rr_ratio:.1f}:1" if s.rr_ratio > 0 else "-",
            rating,
            f"{s.confidence:.0%}",
            s.reason,
        )

    console.print(table)


@app.command()
def backtest(
    symbol: str = typer.Option("SPY", "--symbol", "-s", help="Symbol to backtest"),
    days: int = typer.Option(365, "--days", "-d", help="Days of history"),
    capital: float = typer.Option(100_000, "--capital", "-c", help="Starting capital"),
    risk: float = typer.Option(2.0, "--risk", "-r", help="Risk % per trade"),
):
    """Run backtest with momentum strategy."""
    with console.status(f"Backtesting {symbol} over {days} days..."):
        df = client.get_bars(symbol.upper(), days=days)
        result = run_backtest(df, symbol.upper(), capital, risk)

    console.print(f"\n[bold]Backtest Results — {symbol.upper()}[/bold]")
    console.print(f"  Period: {result.start_date:%Y-%m-%d} to {result.end_date:%Y-%m-%d}")
    console.print(f"  Total Trades: {result.total_trades}")
    console.print(f"  Win Rate: {result.win_rate:.1%}")
    console.print(f"  Avg R:R: {result.avg_rr:.2f}")
    console.print(f"  Total Return: {result.total_return_pct:+.2f}%")
    console.print(f"  Max Drawdown: {result.max_drawdown_pct:.2f}%")

    if result.trades:
        console.print(f"\n[bold]Trade Log ({len(result.trades)} trades):[/bold]")
        table = Table()
        table.add_column("Entry Date", style="dim")
        table.add_column("Exit Date", style="dim")
        table.add_column("Entry", justify="right")
        table.add_column("Exit", justify="right")
        table.add_column("Shares", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Return %", justify="right")

        for t in result.trades:
            pnl_style = "green" if t["pnl"] > 0 else "red"
            table.add_row(
                t["entry_date"][:10],
                t["exit_date"][:10],
                f"${t['entry_price']:.2f}",
                f"${t['exit_price']:.2f}",
                str(t["shares"]),
                f"[{pnl_style}]${t['pnl']:,.2f}[/{pnl_style}]",
                f"[{pnl_style}]{t['return_pct']:+.2f}%[/{pnl_style}]",
            )

        console.print(table)


@app.command("position-size")
def position_size_cmd(
    account: float = typer.Option(..., "--account", "-a", help="Account size in dollars"),
    risk: float = typer.Option(2.0, "--risk", "-r", help="Risk % per trade"),
    entry: float = typer.Option(..., "--entry", "-e", help="Entry price"),
    stop: float = typer.Option(..., "--stop", "-s", help="Stop-loss price"),
    target: Optional[float] = typer.Option(None, "--target", "-t", help="Target price"),
):
    """Calculate position size for a trade."""
    result = calculate_position_size(account, risk, entry, stop, target)
    rating = rate_setup(result.rr_ratio)

    console.print("\n[bold]Position Size Calculator[/bold]")
    console.print(f"  Account Size: ${account:,.2f}")
    console.print(f"  Risk Per Trade: {risk}% (${result.dollar_risk:,.2f})")
    console.print(f"  Entry: ${result.entry_price:.2f}")
    console.print(f"  Stop Loss: ${result.stop_loss:.2f}")
    console.print(f"  Target: ${result.target:.2f}")
    console.print(f"  R:R Ratio: {result.rr_ratio:.1f}:1 ({rating})")
    console.print(f"  Shares: [bold]{result.shares}[/bold]")
    console.print(f"  Position Value: ${result.position_value:,.2f}")


if __name__ == "__main__":
    app()
