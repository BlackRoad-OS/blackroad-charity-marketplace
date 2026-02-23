#!/usr/bin/env python3
"""
Charity & Nonprofit Marketplace
A platform for managing charity registrations, donations, and fundraising campaigns.
"""

import argparse
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


CATEGORIES = ["education", "environment", "health", "housing", "animals", "arts"]


@dataclass
class Charity:
    """Represents a charity or nonprofit organization."""
    id: str
    name: str
    category: str
    description: str
    goal_usd: float
    raised_usd: float
    verified: bool
    created_at: str


@dataclass
class Donation:
    """Represents a donation to a charity."""
    id: str
    charity_id: str
    donor: str
    amount_usd: float
    message: str
    ts: str


class CharityMarketplace:
    """Charity marketplace backend with persistence."""

    DB_PATH = Path.home() / ".blackroad" / "charity.db"

    def __init__(self):
        """Initialize database and create tables if needed."""
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database schema."""
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS charities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    goal_usd REAL NOT NULL,
                    raised_usd REAL NOT NULL DEFAULT 0,
                    verified BOOLEAN NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category ON charities(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_verified ON charities(verified)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS donations (
                    id TEXT PRIMARY KEY,
                    charity_id TEXT NOT NULL,
                    donor TEXT NOT NULL,
                    amount_usd REAL NOT NULL,
                    message TEXT DEFAULT '',
                    ts TEXT NOT NULL,
                    FOREIGN KEY(charity_id) REFERENCES charities(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_charity_id ON donations(charity_id)
            """)
            conn.commit()

    def register_charity(
        self, name: str, category: str, description: str, goal_usd: float
    ) -> Charity:
        """Register a new charity."""
        if category not in CATEGORIES:
            raise ValueError(f"Category must be one of: {', '.join(CATEGORIES)}")

        charity_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO charities (id, name, category, description, goal_usd, raised_usd, verified, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (charity_id, name, category, description, goal_usd, 0, False, now),
            )
            conn.commit()

        return Charity(
            id=charity_id,
            name=name,
            category=category,
            description=description,
            goal_usd=goal_usd,
            raised_usd=0,
            verified=False,
            created_at=now,
        )

    def donate(
        self, charity_id: str, donor: str, amount_usd: float, message: str = ""
    ) -> Donation:
        """Process a donation to a charity."""
        donation_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with sqlite3.connect(self.DB_PATH) as conn:
            # Verify charity exists
            charity = conn.execute(
                "SELECT id FROM charities WHERE id = ?", (charity_id,)
            ).fetchone()
            if not charity:
                raise ValueError(f"Charity {charity_id} not found")

            # Insert donation
            conn.execute(
                """
                INSERT INTO donations (id, charity_id, donor, amount_usd, message, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (donation_id, charity_id, donor, amount_usd, message, now),
            )

            # Update charity raised amount
            conn.execute(
                "UPDATE charities SET raised_usd = raised_usd + ? WHERE id = ?",
                (amount_usd, charity_id),
            )
            conn.commit()

        return Donation(
            id=donation_id,
            charity_id=charity_id,
            donor=donor,
            amount_usd=amount_usd,
            message=message,
            ts=now,
        )

    def get_charities(
        self, category: Optional[str] = None, sort_by: str = "raised"
    ) -> List[Dict[str, Any]]:
        """Get list of charities, optionally filtered by category."""
        sort_field = "raised_usd" if sort_by == "raised" else "created_at"
        sort_order = "DESC" if sort_by == "raised" else "DESC"

        with sqlite3.connect(self.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            if category:
                if category not in CATEGORIES:
                    raise ValueError(f"Category must be one of: {', '.join(CATEGORIES)}")
                query = f"""
                    SELECT * FROM charities WHERE category = ?
                    ORDER BY {sort_field} {sort_order}
                """
                rows = conn.execute(query, (category,)).fetchall()
            else:
                query = f"""
                    SELECT * FROM charities ORDER BY {sort_field} {sort_order}
                """
                rows = conn.execute(query).fetchall()

            return [dict(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Get marketplace statistics."""
        with sqlite3.connect(self.DB_PATH) as conn:
            total_raised, total_charities, total_donations = conn.execute(
                """
                SELECT 
                    COALESCE(SUM(amount_usd), 0) as total_raised,
                    (SELECT COUNT(*) FROM charities) as total_charities,
                    COUNT(*) as total_donations
                FROM donations
                """
            ).fetchone()

            top_charity = conn.execute(
                """
                SELECT id, name, raised_usd FROM charities 
                ORDER BY raised_usd DESC LIMIT 1
                """
            ).fetchone()

        return {
            "total_raised_usd": round(total_raised, 2),
            "total_charities": total_charities,
            "total_donations": total_donations,
            "top_charity": {
                "id": top_charity[0],
                "name": top_charity[1],
                "raised_usd": round(top_charity[2], 2),
            } if top_charity else None,
        }

    def verify_charity(self, charity_id: str) -> Charity:
        """Mark a charity as verified (admin operation)."""
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute(
                "UPDATE charities SET verified = 1 WHERE id = ?", (charity_id,)
            )
            conn.commit()

            charity = conn.execute(
                "SELECT * FROM charities WHERE id = ?", (charity_id,)
            ).fetchone()

        if not charity:
            raise ValueError(f"Charity {charity_id} not found")

        return Charity(*charity)

    def generate_receipt(self, donation_id: str) -> str:
        """Generate a formatted donation receipt."""
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            donation = conn.execute(
                "SELECT * FROM donations WHERE id = ?", (donation_id,)
            ).fetchone()

            if not donation:
                raise ValueError(f"Donation {donation_id} not found")

            charity = conn.execute(
                "SELECT name FROM charities WHERE id = ?", (donation["charity_id"],)
            ).fetchone()

        receipt = f"""
╔════════════════════════════════════════╗
║        DONATION RECEIPT                ║
╚════════════════════════════════════════╝

Receipt ID: {donation_id}
Donor: {donation['donor']}
Charity: {charity[0]}
Amount: ${donation['amount_usd']:.2f}
Date: {donation['ts']}

Message: {donation['message'] or 'N/A'}

Thank you for your generous donation!

════════════════════════════════════════
        Tax ID: pending
        www.blackroad.charity
════════════════════════════════════════
"""
        return receipt.strip()


def main():
    """CLI interface for the charity marketplace."""
    parser = argparse.ArgumentParser(description="Charity Marketplace")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Register charity command
    register_parser = subparsers.add_parser("register", help="Register a new charity")
    register_parser.add_argument("name", help="Charity name")
    register_parser.add_argument("category", help=f"Category: {', '.join(CATEGORIES)}")
    register_parser.add_argument("description", help="Charity description")
    register_parser.add_argument("goal", type=float, help="Fundraising goal in USD")

    # Donate command
    donate_parser = subparsers.add_parser("donate", help="Make a donation")
    donate_parser.add_argument("charity_id", help="Charity ID")
    donate_parser.add_argument("donor", help="Donor name")
    donate_parser.add_argument("amount", type=float, help="Donation amount in USD")
    donate_parser.add_argument("--message", "-m", default="", help="Donation message")

    # List charities command
    list_parser = subparsers.add_parser("list", help="List charities")
    list_parser.add_argument("--category", "-c", help="Filter by category")
    list_parser.add_argument("--sort", "-s", default="raised", help="Sort by: raised or created")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="View marketplace statistics")

    # Verify charity command
    verify_parser = subparsers.add_parser("verify", help="Verify a charity (admin)")
    verify_parser.add_argument("charity_id", help="Charity ID to verify")

    # Receipt command
    receipt_parser = subparsers.add_parser("receipt", help="Generate donation receipt")
    receipt_parser.add_argument("donation_id", help="Donation ID")

    args = parser.parse_args()

    marketplace = CharityMarketplace()

    if args.command == "register":
        charity = marketplace.register_charity(
            args.name, args.category, args.description, args.goal
        )
        print(f"✓ Registered charity: {charity.name}")
        print(f"  ID: {charity.id}")
        print(f"  Category: {charity.category}")
        print(f"  Goal: ${charity.goal_usd:,.2f}")

    elif args.command == "donate":
        donation = marketplace.donate(
            args.charity_id, args.donor, args.amount, message=args.message
        )
        print(f"✓ Donation received!")
        print(f"  Amount: ${donation.amount_usd:.2f}")
        print(f"  Receipt ID: {donation.id}")

    elif args.command == "list":
        charities = marketplace.get_charities(category=args.category, sort_by=args.sort)
        print(f"\n💝 Charities ({len(charities)} total)")
        if args.category:
            print(f"   Category: {args.category}")
        print("─" * 80)
        for charity in charities:
            progress = (charity["raised_usd"] / charity["goal_usd"] * 100) if charity["goal_usd"] > 0 else 0
            verified = "✓" if charity["verified"] else "○"
            print(f"  {verified} {charity['name']}")
            print(f"     Category: {charity['category']}")
            print(f"     Raised: ${charity['raised_usd']:,.2f} / ${charity['goal_usd']:,.2f} ({progress:.1f}%)")
            print(f"     ID: {charity['id']}")
            print()

    elif args.command == "stats":
        stats = marketplace.get_stats()
        print(f"\n📊 Marketplace Statistics:")
        print(f"  Total Raised: ${stats['total_raised_usd']:,.2f}")
        print(f"  Total Charities: {stats['total_charities']}")
        print(f"  Total Donations: {stats['total_donations']}")
        if stats["top_charity"]:
            print(f"  Top Charity: {stats['top_charity']['name']} (${stats['top_charity']['raised_usd']:,.2f})")

    elif args.command == "verify":
        marketplace.verify_charity(args.charity_id)
        print(f"✓ Charity {args.charity_id} verified")

    elif args.command == "receipt":
        receipt = marketplace.generate_receipt(args.donation_id)
        print(receipt)


if __name__ == "__main__":
    main()
