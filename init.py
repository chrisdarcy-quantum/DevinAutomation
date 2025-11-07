#!/usr/bin/env python3
"""
Monolithic Financial Management System
A comprehensive financial portfolio and transaction management application
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import statistics
import re


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class TransactionType(Enum):
    """Types of financial transactions"""
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    INTEREST = "interest"


class AssetType(Enum):
    """Types of financial assets"""
    STOCK = "stock"
    BOND = "bond"
    CRYPTO = "crypto"
    CASH = "cash"
    COMMODITY = "commodity"
    REAL_ESTATE = "real_estate"
    MUTUAL_FUND = "mutual_fund"
    ETF = "etf"


@dataclass
class Asset:
    """Represents a financial asset"""
    symbol: str
    name: str
    asset_type: AssetType
    current_price: float
    quantity: float = 0.0
    average_cost: float = 0.0
    
    @property
    def current_value(self) -> float:
        return self.quantity * self.current_price
    
    @property
    def total_cost(self) -> float:
        return self.quantity * self.average_cost
    
    @property
    def profit_loss(self) -> float:
        return self.current_value - self.total_cost
    
    @property
    def profit_loss_percentage(self) -> float:
        if self.total_cost == 0:
            return 0.0
        return (self.profit_loss / self.total_cost) * 100


@dataclass
class Transaction:
    """Represents a financial transaction"""
    id: Optional[int]
    timestamp: datetime
    transaction_type: TransactionType
    symbol: str
    quantity: float
    price: float
    fee: float = 0.0
    notes: str = ""
    
    @property
    def total_amount(self) -> float:
        if self.transaction_type in [TransactionType.BUY, TransactionType.WITHDRAWAL]:
            return (self.quantity * self.price) + self.fee
        else:
            return (self.quantity * self.price) - self.fee


@dataclass
class Portfolio:
    """Represents an investment portfolio"""
    name: str
    assets: Dict[str, Asset]
    cash_balance: float = 0.0
    
    @property
    def total_value(self) -> float:
        return sum(asset.current_value for asset in self.assets.values()) + self.cash_balance
    
    @property
    def total_invested(self) -> float:
        return sum(asset.total_cost for asset in self.assets.values())
    
    @property
    def total_profit_loss(self) -> float:
        return sum(asset.profit_loss for asset in self.assets.values())
    
    @property
    def total_profit_loss_percentage(self) -> float:
        if self.total_invested == 0:
            return 0.0
        return (self.total_profit_loss / self.total_invested) * 100


# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path: str = "financial_system.db"):
        self.db_path = db_path
        self.conn = None
        self.initialize_database()
    
    def initialize_database(self):
        """Create database tables if they don't exist"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # Create transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                fee REAL DEFAULT 0.0,
                notes TEXT
            )
        """)
        
        # Create assets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                current_price REAL NOT NULL,
                quantity REAL DEFAULT 0.0,
                average_cost REAL DEFAULT 0.0
            )
        """)
        
        # Create portfolio metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_metadata (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL,
                cash_balance REAL DEFAULT 0.0
            )
        """)
        
        # Insert default portfolio if not exists
        cursor.execute("SELECT COUNT(*) FROM portfolio_metadata")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO portfolio_metadata (id, name, cash_balance)
                VALUES (1, 'Main Portfolio', 0.0)
            """)
        
        self.conn.commit()
    
    def add_transaction(self, transaction: Transaction) -> int:
        """Add a transaction to the database"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (timestamp, transaction_type, symbol, quantity, price, fee, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction.timestamp.isoformat(),
            transaction.transaction_type.value,
            transaction.symbol,
            transaction.quantity,
            transaction.price,
            transaction.fee,
            transaction.notes
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_all_transactions(self) -> List[Transaction]:
        """Retrieve all transactions"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, transaction_type, symbol, quantity, price, fee, notes
            FROM transactions
            ORDER BY timestamp DESC
        """)
        
        transactions = []
        for row in cursor.fetchall():
            transactions.append(Transaction(
                id=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                transaction_type=TransactionType(row[2]),
                symbol=row[3],
                quantity=row[4],
                price=row[5],
                fee=row[6],
                notes=row[7]
            ))
        return transactions
    
    def get_transactions_by_symbol(self, symbol: str) -> List[Transaction]:
        """Get all transactions for a specific symbol"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, transaction_type, symbol, quantity, price, fee, notes
            FROM transactions
            WHERE symbol = ?
            ORDER BY timestamp DESC
        """, (symbol,))
        
        transactions = []
        for row in cursor.fetchall():
            transactions.append(Transaction(
                id=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                transaction_type=TransactionType(row[2]),
                symbol=row[3],
                quantity=row[4],
                price=row[5],
                fee=row[6],
                notes=row[7]
            ))
        return transactions
    
    def update_asset(self, asset: Asset):
        """Update or insert an asset"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO assets (symbol, name, asset_type, current_price, quantity, average_cost)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            asset.symbol,
            asset.name,
            asset.asset_type.value,
            asset.current_price,
            asset.quantity,
            asset.average_cost
        ))
        self.conn.commit()
    
    def get_all_assets(self) -> Dict[str, Asset]:
        """Retrieve all assets"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT symbol, name, asset_type, current_price, quantity, average_cost FROM assets")
        
        assets = {}
        for row in cursor.fetchall():
            asset = Asset(
                symbol=row[0],
                name=row[1],
                asset_type=AssetType(row[2]),
                current_price=row[3],
                quantity=row[4],
                average_cost=row[5]
            )
            assets[asset.symbol] = asset
        return assets
    
    def get_asset(self, symbol: str) -> Optional[Asset]:
        """Get a specific asset by symbol"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT symbol, name, asset_type, current_price, quantity, average_cost
            FROM assets WHERE symbol = ?
        """, (symbol,))
        
        row = cursor.fetchone()
        if row:
            return Asset(
                symbol=row[0],
                name=row[1],
                asset_type=AssetType(row[2]),
                current_price=row[3],
                quantity=row[4],
                average_cost=row[5]
            )
        return None
    
    def update_cash_balance(self, amount: float):
        """Update the cash balance"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE portfolio_metadata SET cash_balance = cash_balance + ? WHERE id = 1
        """, (amount,))
        self.conn.commit()
    
    def get_cash_balance(self) -> float:
        """Get current cash balance"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT cash_balance FROM portfolio_metadata WHERE id = 1")
        result = cursor.fetchone()
        return result[0] if result else 0.0
    
    def get_portfolio_name(self) -> str:
        """Get portfolio name"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM portfolio_metadata WHERE id = 1")
        result = cursor.fetchone()
        return result[0] if result else "Main Portfolio"
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


# ============================================================================
# PORTFOLIO MANAGER
# ============================================================================

class PortfolioManager:
    """Manages portfolio operations and transactions"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def buy_asset(self, symbol: str, name: str, asset_type: AssetType, 
                  quantity: float, price: float, fee: float = 0.0, notes: str = "") -> bool:
        """Buy an asset"""
        total_cost = (quantity * price) + fee
        
        # Check if sufficient cash
        if self.db.get_cash_balance() < total_cost:
            print(f"Insufficient funds. Need ${total_cost:.2f}, have ${self.db.get_cash_balance():.2f}")
            return False
        
        # Create transaction
        transaction = Transaction(
            id=None,
            timestamp=datetime.now(),
            transaction_type=TransactionType.BUY,
            symbol=symbol,
            quantity=quantity,
            price=price,
            fee=fee,
            notes=notes
        )
        self.db.add_transaction(transaction)
        
        # Update asset
        asset = self.db.get_asset(symbol)
        if asset:
            # Calculate new average cost
            total_quantity = asset.quantity + quantity
            total_cost_basis = (asset.quantity * asset.average_cost) + (quantity * price) + fee
            new_average_cost = total_cost_basis / total_quantity
            
            asset.quantity = total_quantity
            asset.average_cost = new_average_cost
            asset.current_price = price
        else:
            # Create new asset
            asset = Asset(
                symbol=symbol,
                name=name,
                asset_type=asset_type,
                current_price=price,
                quantity=quantity,
                average_cost=(quantity * price + fee) / quantity
            )
        
        self.db.update_asset(asset)
        
        # Update cash balance
        self.db.update_cash_balance(-total_cost)
        
        print(f"✓ Bought {quantity} shares of {symbol} at ${price:.2f} per share (Fee: ${fee:.2f})")
        return True
    
    def sell_asset(self, symbol: str, quantity: float, price: float, 
                   fee: float = 0.0, notes: str = "") -> bool:
        """Sell an asset"""
        asset = self.db.get_asset(symbol)
        
        if not asset:
            print(f"Asset {symbol} not found in portfolio")
            return False
        
        if asset.quantity < quantity:
            print(f"Insufficient quantity. Have {asset.quantity}, trying to sell {quantity}")
            return False
        
        # Create transaction
        transaction = Transaction(
            id=None,
            timestamp=datetime.now(),
            transaction_type=TransactionType.SELL,
            symbol=symbol,
            quantity=quantity,
            price=price,
            fee=fee,
            notes=notes
        )
        self.db.add_transaction(transaction)
        
        # Update asset
        asset.quantity -= quantity
        if asset.quantity == 0:
            asset.average_cost = 0
        
        self.db.update_asset(asset)
        
        # Update cash balance
        proceeds = (quantity * price) - fee
        self.db.update_cash_balance(proceeds)
        
        realized_profit = (price - asset.average_cost) * quantity - fee
        print(f"✓ Sold {quantity} shares of {symbol} at ${price:.2f} per share (Fee: ${fee:.2f})")
        print(f"  Realized P/L: ${realized_profit:.2f}")
        return True
    
    def add_dividend(self, symbol: str, amount: float, notes: str = "") -> bool:
        """Record a dividend payment"""
        transaction = Transaction(
            id=None,
            timestamp=datetime.now(),
            transaction_type=TransactionType.DIVIDEND,
            symbol=symbol,
            quantity=1,
            price=amount,
            fee=0.0,
            notes=notes
        )
        self.db.add_transaction(transaction)
        self.db.update_cash_balance(amount)
        
        print(f"✓ Recorded dividend of ${amount:.2f} from {symbol}")
        return True
    
    def deposit_cash(self, amount: float, notes: str = "") -> bool:
        """Deposit cash into portfolio"""
        transaction = Transaction(
            id=None,
            timestamp=datetime.now(),
            transaction_type=TransactionType.DEPOSIT,
            symbol="CASH",
            quantity=1,
            price=amount,
            fee=0.0,
            notes=notes
        )
        self.db.add_transaction(transaction)
        self.db.update_cash_balance(amount)
        
        print(f"✓ Deposited ${amount:.2f}")
        return True
    
    def withdraw_cash(self, amount: float, notes: str = "") -> bool:
        """Withdraw cash from portfolio"""
        if self.db.get_cash_balance() < amount:
            print(f"Insufficient funds. Have ${self.db.get_cash_balance():.2f}")
            return False
        
        transaction = Transaction(
            id=None,
            timestamp=datetime.now(),
            transaction_type=TransactionType.WITHDRAWAL,
            symbol="CASH",
            quantity=1,
            price=amount,
            fee=0.0,
            notes=notes
        )
        self.db.add_transaction(transaction)
        self.db.update_cash_balance(-amount)
        
        print(f"✓ Withdrew ${amount:.2f}")
        return True
    
    def update_asset_price(self, symbol: str, new_price: float) -> bool:
        """Update the current price of an asset"""
        asset = self.db.get_asset(symbol)
        if not asset:
            print(f"Asset {symbol} not found")
            return False
        
        asset.current_price = new_price
        self.db.update_asset(asset)
        print(f"✓ Updated {symbol} price to ${new_price:.2f}")
        return True
    
    def get_portfolio(self) -> Portfolio:
        """Get current portfolio state"""
        return Portfolio(
            name=self.db.get_portfolio_name(),
            assets=self.db.get_all_assets(),
            cash_balance=self.db.get_cash_balance()
        )


# ============================================================================
# ANALYTICS ENGINE
# ============================================================================

class AnalyticsEngine:
    """Provides financial analytics and reporting"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def calculate_asset_allocation(self, portfolio: Portfolio) -> Dict[AssetType, float]:
        """Calculate asset allocation by type"""
        allocation = {}
        total_value = portfolio.total_value
        
        if total_value == 0:
            return allocation
        
        # Group by asset type
        for asset in portfolio.assets.values():
            asset_value = asset.current_value
            percentage = (asset_value / total_value) * 100
            
            if asset.asset_type in allocation:
                allocation[asset.asset_type] += percentage
            else:
                allocation[asset.asset_type] = percentage
        
        # Add cash allocation
        if portfolio.cash_balance > 0:
            cash_percentage = (portfolio.cash_balance / total_value) * 100
            allocation[AssetType.CASH] = cash_percentage
        
        return allocation
    
    def get_top_performers(self, portfolio: Portfolio, limit: int = 5) -> List[Tuple[str, float]]:
        """Get top performing assets by profit/loss percentage"""
        performers = []
        for symbol, asset in portfolio.assets.items():
            if asset.quantity > 0:
                performers.append((symbol, asset.profit_loss_percentage))
        
        performers.sort(key=lambda x: x[1], reverse=True)
        return performers[:limit]
    
    def get_bottom_performers(self, portfolio: Portfolio, limit: int = 5) -> List[Tuple[str, float]]:
        """Get worst performing assets by profit/loss percentage"""
        performers = []
        for symbol, asset in portfolio.assets.items():
            if asset.quantity > 0:
                performers.append((symbol, asset.profit_loss_percentage))
        
        performers.sort(key=lambda x: x[1])
        return performers[:limit]
    
    def calculate_diversification_score(self, portfolio: Portfolio) -> float:
        """Calculate portfolio diversification score (0-100)"""
        if len(portfolio.assets) == 0:
            return 0.0
        
        allocations = []
        total_value = portfolio.total_value
        
        for asset in portfolio.assets.values():
            if asset.quantity > 0:
                percentage = (asset.current_value / total_value) * 100
                allocations.append(percentage)
        
        if len(allocations) <= 1:
            return 0.0
        
        # Use standard deviation to measure concentration
        std_dev = statistics.stdev(allocations)
        mean = statistics.mean(allocations)
        
        # Coefficient of variation (lower is more diversified)
        cv = std_dev / mean if mean > 0 else 0
        
        # Convert to score (0-100, where 100 is perfectly diversified)
        # Assuming CV > 2 means poor diversification
        score = max(0, min(100, (1 - min(cv / 2, 1)) * 100))
        
        return score
    
    def get_transaction_summary(self, days: int = 30) -> Dict[str, any]:
        """Get summary of transactions for the last N days"""
        all_transactions = self.db.get_all_transactions()
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_transactions = [t for t in all_transactions if t.timestamp >= cutoff_date]
        
        summary = {
            'total_transactions': len(recent_transactions),
            'buys': len([t for t in recent_transactions if t.transaction_type == TransactionType.BUY]),
            'sells': len([t for t in recent_transactions if t.transaction_type == TransactionType.SELL]),
            'dividends': len([t for t in recent_transactions if t.transaction_type == TransactionType.DIVIDEND]),
            'total_invested': sum(t.total_amount for t in recent_transactions if t.transaction_type == TransactionType.BUY),
            'total_divested': sum(t.total_amount for t in recent_transactions if t.transaction_type == TransactionType.SELL),
            'total_dividends': sum(t.price for t in recent_transactions if t.transaction_type == TransactionType.DIVIDEND),
            'total_fees': sum(t.fee for t in recent_transactions)
        }
        
        return summary
    
    def calculate_portfolio_volatility(self, portfolio: Portfolio) -> float:
        """Calculate portfolio volatility based on asset price changes"""
        # This is a simplified version - in reality, you'd use historical price data
        returns = []
        
        for symbol, asset in portfolio.assets.items():
            if asset.quantity > 0 and asset.average_cost > 0:
                # Calculate return percentage
                ret = ((asset.current_price - asset.average_cost) / asset.average_cost) * 100
                returns.append(ret)
        
        if len(returns) < 2:
            return 0.0
        
        return statistics.stdev(returns)
    
    def generate_tax_report(self, year: int) -> Dict[str, any]:
        """Generate tax report for realized gains/losses"""
        all_transactions = self.db.get_all_transactions()
        
        # Filter transactions for the specified year
        year_transactions = [
            t for t in all_transactions 
            if t.timestamp.year == year and t.transaction_type == TransactionType.SELL
        ]
        
        total_realized_gains = 0.0
        total_realized_losses = 0.0
        
        for sell_transaction in year_transactions:
            # Get the asset's average cost at time of sale
            asset = self.db.get_asset(sell_transaction.symbol)
            if asset:
                cost_basis = asset.average_cost * sell_transaction.quantity
                proceeds = sell_transaction.quantity * sell_transaction.price - sell_transaction.fee
                gain_loss = proceeds - cost_basis
                
                if gain_loss > 0:
                    total_realized_gains += gain_loss
                else:
                    total_realized_losses += abs(gain_loss)
        
        # Calculate dividend income
        dividend_transactions = [
            t for t in all_transactions
            if t.timestamp.year == year and t.transaction_type == TransactionType.DIVIDEND
        ]
        total_dividends = sum(t.price for t in dividend_transactions)
        
        return {
            'year': year,
            'realized_gains': total_realized_gains,
            'realized_losses': total_realized_losses,
            'net_capital_gains': total_realized_gains - total_realized_losses,
            'dividend_income': total_dividends,
            'taxable_income': total_realized_gains - total_realized_losses + total_dividends,
            'number_of_sales': len(year_transactions),
            'number_of_dividends': len(dividend_transactions)
        }


# ============================================================================
# REPORTING SYSTEM
# ============================================================================

class ReportingSystem:
    """Generate various financial reports"""
    
    def __init__(self, portfolio_manager: PortfolioManager, analytics: AnalyticsEngine):
        self.pm = portfolio_manager
        self.analytics = analytics
    
    def print_portfolio_summary(self):
        """Print comprehensive portfolio summary"""
        portfolio = self.pm.get_portfolio()
        
        print("\n" + "="*80)
        print(f"  {portfolio.name.upper()} - PORTFOLIO SUMMARY")
        print("="*80)
        
        # Overall metrics
        print(f"\n📊 OVERALL PORTFOLIO METRICS")
        print(f"   Total Value:           ${portfolio.total_value:,.2f}")
        print(f"   Cash Balance:          ${portfolio.cash_balance:,.2f}")
        print(f"   Total Invested:        ${portfolio.total_invested:,.2f}")
        print(f"   Total P/L:             ${portfolio.total_profit_loss:,.2f} ({portfolio.total_profit_loss_percentage:+.2f}%)")
        
        # Asset allocation
        print(f"\n💼 ASSET ALLOCATION")
        allocation = self.analytics.calculate_asset_allocation(portfolio)
        for asset_type, percentage in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
            print(f"   {asset_type.value.replace('_', ' ').title():20} {percentage:6.2f}%")
        
        # Diversification score
        div_score = self.analytics.calculate_diversification_score(portfolio)
        print(f"\n🎯 DIVERSIFICATION SCORE: {div_score:.1f}/100")
        
        # Individual holdings
        print(f"\n📈 HOLDINGS ({len([a for a in portfolio.assets.values() if a.quantity > 0])} positions)")
        print(f"   {'Symbol':<10} {'Qty':>10} {'Avg Cost':>12} {'Curr Price':>12} {'Value':>15} {'P/L':>15} {'P/L %':>10}")
        print(f"   {'-'*88}")
        
        for symbol in sorted(portfolio.assets.keys()):
            asset = portfolio.assets[symbol]
            if asset.quantity > 0:
                pl_symbol = "+" if asset.profit_loss >= 0 else ""
                print(f"   {asset.symbol:<10} {asset.quantity:>10.2f} "
                      f"${asset.average_cost:>11.2f} ${asset.current_price:>11.2f} "
                      f"${asset.current_value:>14,.2f} "
                      f"{pl_symbol}${asset.profit_loss:>13,.2f} "
                      f"{asset.profit_loss_percentage:>9.2f}%")
        
        print("="*80 + "\n")
    
    def print_top_performers(self, limit: int = 5):
        """Print top performing assets"""
        portfolio = self.pm.get_portfolio()
        top = self.analytics.get_top_performers(portfolio, limit)
        
        print(f"\n🏆 TOP {limit} PERFORMERS")
        print(f"   {'Symbol':<10} {'P/L %':>10}")
        print(f"   {'-'*22}")
        for symbol, percentage in top:
            print(f"   {symbol:<10} {percentage:>9.2f}%")
    
    def print_bottom_performers(self, limit: int = 5):
        """Print worst performing assets"""
        portfolio = self.pm.get_portfolio()
        bottom = self.analytics.get_bottom_performers(portfolio, limit)
        
        print(f"\n📉 BOTTOM {limit} PERFORMERS")
        print(f"   {'Symbol':<10} {'P/L %':>10}")
        print(f"   {'-'*22}")
        for symbol, percentage in bottom:
            print(f"   {symbol:<10} {percentage:>9.2f}%")
    
    def print_transaction_history(self, limit: int = 10):
        """Print recent transaction history"""
        transactions = self.pm.db.get_all_transactions()[:limit]
        
        print(f"\n📜 RECENT TRANSACTIONS (Last {limit})")
        print(f"   {'Date':<12} {'Type':<12} {'Symbol':<10} {'Qty':>10} {'Price':>12} {'Total':>15}")
        print(f"   {'-'*78}")
        
        for t in transactions:
            date_str = t.timestamp.strftime("%Y-%m-%d")
            total = t.total_amount if t.transaction_type in [TransactionType.BUY, TransactionType.SELL] else t.price
            print(f"   {date_str:<12} {t.transaction_type.value:<12} {t.symbol:<10} "
                  f"{t.quantity:>10.2f} ${t.price:>11.2f} ${total:>14,.2f}")
    
    def print_transaction_summary(self, days: int = 30):
        """Print transaction summary for period"""
        summary = self.analytics.get_transaction_summary(days)
        
        print(f"\n📊 TRANSACTION SUMMARY (Last {days} days)")
        print(f"   Total Transactions:    {summary['total_transactions']}")
        print(f"   Buy Transactions:      {summary['buys']}")
        print(f"   Sell Transactions:     {summary['sells']}")
        print(f"   Dividends Received:    {summary['dividends']}")
        print(f"   Total Invested:        ${summary['total_invested']:,.2f}")
        print(f"   Total Divested:        ${summary['total_divested']:,.2f}")
        print(f"   Dividend Income:       ${summary['total_dividends']:,.2f}")
        print(f"   Total Fees Paid:       ${summary['total_fees']:,.2f}")
    
    def print_tax_report(self, year: int):
        """Print tax report"""
        report = self.analytics.generate_tax_report(year)
        
        print(f"\n💰 TAX REPORT FOR {year}")
        print(f"   Realized Capital Gains:    ${report['realized_gains']:,.2f}")
        print(f"   Realized Capital Losses:   ${report['realized_losses']:,.2f}")
        print(f"   Net Capital Gains:         ${report['net_capital_gains']:,.2f}")
        print(f"   Dividend Income:           ${report['dividend_income']:,.2f}")
        print(f"   Total Taxable Income:      ${report['taxable_income']:,.2f}")
        print(f"   Number of Sales:           {report['number_of_sales']}")
        print(f"   Number of Dividends:       {report['number_of_dividends']}")
    
    def export_to_json(self, filename: str = "portfolio_export.json"):
        """Export portfolio data to JSON"""
        portfolio = self.pm.get_portfolio()
        transactions = self.pm.db.get_all_transactions()
        
        data = {
            'portfolio': {
                'name': portfolio.name,
                'cash_balance': portfolio.cash_balance,
                'total_value': portfolio.total_value,
                'total_invested': portfolio.total_invested,
                'total_profit_loss': portfolio.total_profit_loss
            },
            'assets': [
                {
                    'symbol': asset.symbol,
                    'name': asset.name,
                    'type': asset.asset_type.value,
                    'quantity': asset.quantity,
                    'current_price': asset.current_price,
                    'average_cost': asset.average_cost,
                    'current_value': asset.current_value,
                    'profit_loss': asset.profit_loss
                }
                for asset in portfolio.assets.values() if asset.quantity > 0
            ],
            'transactions': [
                {
                    'id': t.id,
                    'timestamp': t.timestamp.isoformat(),
                    'type': t.transaction_type.value,
                    'symbol': t.symbol,
                    'quantity': t.quantity,
                    'price': t.price,
                    'fee': t.fee,
                    'notes': t.notes
                }
                for t in transactions
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✓ Portfolio exported to {filename}")


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

class FinancialSystemCLI:
    """Command-line interface for the financial system"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.pm = PortfolioManager(self.db)
        self.analytics = AnalyticsEngine(self.db)
        self.reporting = ReportingSystem(self.pm, self.analytics)
    
    def run(self):
        """Run the CLI"""
        print("\n" + "="*80)
        print("  MONOLITHIC FINANCIAL MANAGEMENT SYSTEM")
        print("="*80)
        
        while True:
            print("\n📋 MAIN MENU")
            print("   1.  View Portfolio Summary")
            print("   2.  Buy Asset")
            print("   3.  Sell Asset")
            print("   4.  Record Dividend")
            print("   5.  Deposit Cash")
            print("   6.  Withdraw Cash")
            print("   7.  Update Asset Price")
            print("   8.  View Transaction History")
            print("   9.  View Transaction Summary")
            print("   10. View Top Performers")
            print("   11. View Bottom Performers")
            print("   12. Generate Tax Report")
            print("   13. Export Portfolio to JSON")
            print("   14. Exit")
            
            choice = input("\n   Enter your choice (1-14): ").strip()
            
            if choice == "1":
                self.reporting.print_portfolio_summary()
            elif choice == "2":
                self.buy_asset_menu()
            elif choice == "3":
                self.sell_asset_menu()
            elif choice == "4":
                self.record_dividend_menu()
            elif choice == "5":
                self.deposit_cash_menu()
            elif choice == "6":
                self.withdraw_cash_menu()
            elif choice == "7":
                self.update_price_menu()
            elif choice == "8":
                limit = input("   Number of transactions to show (default 10): ").strip()
                limit = int(limit) if limit.isdigit() else 10
                self.reporting.print_transaction_history(limit)
            elif choice == "9":
                days = input("   Number of days to summarize (default 30): ").strip()
                days = int(days) if days.isdigit() else 30
                self.reporting.print_transaction_summary(days)
            elif choice == "10":
                limit = input("   Number of top performers to show (default 5): ").strip()
                limit = int(limit) if limit.isdigit() else 5
                self.reporting.print_top_performers(limit)
            elif choice == "11":
                limit = input("   Number of bottom performers to show (default 5): ").strip()
                limit = int(limit) if limit.isdigit() else 5
                self.reporting.print_bottom_performers(limit)
            elif choice == "12":
                year = input("   Year for tax report (default current year): ").strip()
                year = int(year) if year.isdigit() else datetime.now().year
                self.reporting.print_tax_report(year)
            elif choice == "13":
                filename = input("   Filename (default: portfolio_export.json): ").strip()
                filename = filename if filename else "portfolio_export.json"
                self.reporting.export_to_json(filename)
            elif choice == "14":
                print("\n   Thank you for using the Financial Management System!")
                self.db.close()
                break
            else:
                print("   ❌ Invalid choice. Please try again.")
    
    def buy_asset_menu(self):
        """Menu for buying assets"""
        print("\n💰 BUY ASSET")
        symbol = input("   Symbol: ").strip().upper()
        name = input("   Name: ").strip()
        
        print("   Asset Types:")
        for i, at in enumerate(AssetType, 1):
            print(f"     {i}. {at.value}")
        
        type_choice = input("   Asset Type (1-8): ").strip()
        try:
            asset_type = list(AssetType)[int(type_choice) - 1]
        except (ValueError, IndexError):
            print("   ❌ Invalid asset type")
            return
        
        try:
            quantity = float(input("   Quantity: ").strip())
            price = float(input("   Price per unit: ").strip())
            fee = float(input("   Fee (default 0): ").strip() or "0")
            notes = input("   Notes (optional): ").strip()
            
            self.pm.buy_asset(symbol, name, asset_type, quantity, price, fee, notes)
        except ValueError:
            print("   ❌ Invalid numeric input")
    
    def sell_asset_menu(self):
        """Menu for selling assets"""
        print("\n💸 SELL ASSET")
        symbol = input("   Symbol: ").strip().upper()
        
        try:
            quantity = float(input("   Quantity: ").strip())
            price = float(input("   Price per unit: ").strip())
            fee = float(input("   Fee (default 0): ").strip() or "0")
            notes = input("   Notes (optional): ").strip()
            
            self.pm.sell_asset(symbol, quantity, price, fee, notes)
        except ValueError:
            print("   ❌ Invalid numeric input")
    
    def record_dividend_menu(self):
        """Menu for recording dividends"""
        print("\n💵 RECORD DIVIDEND")
        symbol = input("   Symbol: ").strip().upper()
        
        try:
            amount = float(input("   Dividend amount: ").strip())
            notes = input("   Notes (optional): ").strip()
            
            self.pm.add_dividend(symbol, amount, notes)
        except ValueError:
            print("   ❌ Invalid numeric input")
    
    def deposit_cash_menu(self):
        """Menu for depositing cash"""
        print("\n💰 DEPOSIT CASH")
        
        try:
            amount = float(input("   Amount: ").strip())
            notes = input("   Notes (optional): ").strip()
            
            self.pm.deposit_cash(amount, notes)
        except ValueError:
            print("   ❌ Invalid numeric input")
    
    def withdraw_cash_menu(self):
        """Menu for withdrawing cash"""
        print("\n💸 WITHDRAW CASH")
        
        try:
            amount = float(input("   Amount: ").strip())
            notes = input("   Notes (optional): ").strip()
            
            self.pm.withdraw_cash(amount, notes)
        except ValueError:
            print("   ❌ Invalid numeric input")
    
    def update_price_menu(self):
        """Menu for updating asset prices"""
        print("\n📊 UPDATE ASSET PRICE")
        symbol = input("   Symbol: ").strip().upper()
        
        try:
            price = float(input("   New price: ").strip())
            self.pm.update_asset_price(symbol, price)
        except ValueError:
            print("   ❌ Invalid numeric input")


# ============================================================================
# DEMO / TESTING FUNCTIONS
# ============================================================================

def run_demo():
    """Run a demo with sample data"""
    print("\n🎮 Running Demo with Sample Data...")
    
    db = DatabaseManager("demo_financial_system.db")
    pm = PortfolioManager(db)
    analytics = AnalyticsEngine(db)
    reporting = ReportingSystem(pm, analytics)
    
    # Deposit initial cash
    pm.deposit_cash(50000, "Initial investment")
    
    # Buy some assets
    pm.buy_asset("AAPL", "Apple Inc.", AssetType.STOCK, 50, 150.00, 9.99, "Tech stock")
    pm.buy_asset("MSFT", "Microsoft Corp.", AssetType.STOCK, 30, 300.00, 9.99, "Tech stock")
    pm.buy_asset("GOOGL", "Alphabet Inc.", AssetType.STOCK, 20, 140.00, 9.99, "Tech stock")
    pm.buy_asset("BTC", "Bitcoin", AssetType.CRYPTO, 0.5, 40000.00, 50.00, "Cryptocurrency")
    pm.buy_asset("GLD", "Gold ETF", AssetType.ETF, 100, 180.00, 9.99, "Precious metals")
    pm.buy_asset("AGG", "Bond ETF", AssetType.BOND, 200, 110.00, 9.99, "Fixed income")
    
    # Update some prices to simulate market movement
    pm.update_asset_price("AAPL", 165.00)
    pm.update_asset_price("MSFT", 320.00)
    pm.update_asset_price("GOOGL", 135.00)
    pm.update_asset_price("BTC", 45000.00)
    pm.update_asset_price("GLD", 185.00)
    pm.update_asset_price("AGG", 108.00)
    
    # Record some dividends
    pm.add_dividend("AAPL", 22.50, "Quarterly dividend")
    pm.add_dividend("MSFT", 18.00, "Quarterly dividend")
    
    # Sell some assets
    pm.sell_asset("GOOGL", 10, 138.00, 9.99, "Taking profits")
    
    # Print comprehensive reports
    reporting.print_portfolio_summary()
    reporting.print_top_performers()
    reporting.print_bottom_performers()
    reporting.print_transaction_history(20)
    reporting.print_transaction_summary(30)
    reporting.print_tax_report(2025)
    
    # Export to JSON
    reporting.export_to_json("demo_portfolio.json")
    
    db.close()
    print("\n✓ Demo completed!")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        run_demo()
    else:
        cli = FinancialSystemCLI()
        cli.run()


if __name__ == "__main__":
    main()
