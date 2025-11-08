# DevinAutomation - Financial Management System

A comprehensive monolithic financial portfolio and transaction management application built in Python.

## Overview

This application provides a complete financial management system with features for tracking investments, managing transactions, analyzing portfolio performance, and generating reports. It uses SQLite for data persistence and includes a command-line interface for easy interaction.

## Features

### Core Functionality
- **Portfolio Management**: Track multiple asset types including stocks, bonds, crypto, ETFs, mutual funds, commodities, and real estate
- **Transaction Management**: Record buys, sells, dividends, deposits, withdrawals, and fees
- **Real-time Portfolio Tracking**: Monitor current values, profit/loss, and performance metrics
- **Cash Management**: Deposit and withdraw cash with full transaction history

### Analytics & Reporting
- **Asset Allocation Analysis**: View portfolio distribution by asset type
- **Performance Tracking**: Identify top and bottom performers
- **Diversification Scoring**: Calculate portfolio diversification metrics (0-100 scale)
- **Transaction Summaries**: Analyze trading activity over custom time periods
- **Tax Reporting**: Generate annual tax reports for realized gains/losses and dividend income
- **Portfolio Volatility**: Calculate portfolio volatility metrics

### Data Management
- **SQLite Database**: Persistent storage for all transactions and assets
- **JSON Export**: Export complete portfolio data to JSON format
- **Transaction History**: Complete audit trail of all portfolio activities

## Requirements

- Python 3.7 or higher
- Standard library modules only (no external dependencies required)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/chrisdarcy-quantum/DevinAutomation.git
cd DevinAutomation
```

2. The application uses only Python standard library modules, so no additional installation is required.

## Usage

### Interactive CLI Mode

Run the application in interactive mode:

```bash
python3 init.py
```

This will launch the interactive menu where you can:
1. View Portfolio Summary
2. Buy Asset
3. Sell Asset
4. Record Dividend
5. Deposit Cash
6. Withdraw Cash
7. Update Asset Price
8. View Transaction History
9. View Transaction Summary
10. View Top Performers
11. View Bottom Performers
12. Generate Tax Report
13. Export Portfolio to JSON
14. Exit

### Demo Mode

Run a demonstration with sample data:

```bash
python3 init.py --demo
```

This will create a demo portfolio with sample transactions and generate comprehensive reports.

## Architecture

The application is structured as a monolithic system with the following components:

### Data Models
- **Asset**: Represents financial assets with properties like symbol, name, type, price, quantity, and cost basis
- **Transaction**: Records all financial transactions with timestamps and details
- **Portfolio**: Aggregates assets and cash balance with calculated metrics

### Core Classes
- **DatabaseManager**: Handles all SQLite database operations and data persistence
- **PortfolioManager**: Manages portfolio operations including buying, selling, and updating assets
- **AnalyticsEngine**: Provides financial analytics and calculations
- **ReportingSystem**: Generates formatted reports and exports
- **FinancialSystemCLI**: Command-line interface for user interaction

### Asset Types Supported
- Stocks
- Bonds
- Cryptocurrency
- Cash
- Commodities
- Real Estate
- Mutual Funds
- ETFs

### Transaction Types
- Buy
- Sell
- Dividend
- Deposit
- Withdrawal
- Fee
- Interest

## Database Schema

The application uses three main tables:

1. **transactions**: Stores all transaction records
2. **assets**: Stores current asset holdings and prices
3. **portfolio_metadata**: Stores portfolio name and cash balance

## Example Workflow

```python
# Initialize the system
db = DatabaseManager()
pm = PortfolioManager(db)
analytics = AnalyticsEngine(db)
reporting = ReportingSystem(pm, analytics)

# Deposit initial cash
pm.deposit_cash(10000, "Initial investment")

# Buy assets
pm.buy_asset("AAPL", "Apple Inc.", AssetType.STOCK, 10, 150.00, 9.99, "Tech stock")
pm.buy_asset("BTC", "Bitcoin", AssetType.CRYPTO, 0.1, 40000.00, 50.00, "Crypto")

# Update prices
pm.update_asset_price("AAPL", 165.00)
pm.update_asset_price("BTC", 45000.00)

# Record dividend
pm.add_dividend("AAPL", 5.00, "Quarterly dividend")

# Generate reports
reporting.print_portfolio_summary()
reporting.print_top_performers()
reporting.export_to_json("my_portfolio.json")

# Close database
db.close()
```

## Data Files

- `financial_system.db`: Main database file (created automatically)
- `demo_financial_system.db`: Demo database file (created when running demo mode)
- `portfolio_export.json`: Default export filename (customizable)

## Performance Metrics

The system calculates various performance metrics:

- **Current Value**: Real-time portfolio valuation
- **Total Invested**: Sum of all purchase costs
- **Profit/Loss**: Unrealized gains/losses on current holdings
- **Profit/Loss Percentage**: Return on investment percentage
- **Diversification Score**: Portfolio concentration metric (0-100)
- **Asset Allocation**: Percentage breakdown by asset type

## Tax Reporting

The tax report feature generates:
- Realized capital gains
- Realized capital losses
- Net capital gains/losses
- Dividend income
- Total taxable income
- Transaction counts

## Contributing

This is a demonstration project. For contributions or issues, please contact the repository owner.

## License

This project is provided as-is for educational and demonstration purposes.

## Author

Chris Darcy (Chris.darcy5@gmail.com)

## Repository

https://github.com/chrisdarcy-quantum/DevinAutomation
