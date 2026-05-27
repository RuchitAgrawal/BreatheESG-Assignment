"""
Seed management command: creates 3 demo organizations with pre-ingested data.

Usage:
    python manage.py seed_demo

Demo accounts:
    demo@acme.com     / demo123  (Acme Corp)    -- mixed states, can click Lock for Audit
    analyst@globex.com / demo123  (Globex Corp)  -- needs_review records waiting for approval
    admin@initech.com  / demo123  (Initech Ltd)  -- shows error handling

Run this after: python manage.py migrate && python manage.py loaddata emission_factors
"""

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Organization, User
from apps.ingestion.service import ingest_sap, ingest_utility, ingest_travel
from apps.records.models import ActivityRecord


FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "fixtures"

DEMO_ORGS = [
    {
        "name": "Acme Corp",
        "slug": "acme",
        "email": "demo@acme.com",
        "password": "demo123",
        "role": "analyst",
        "first_name": "Alex",
        "last_name": "Demo",
        "description": "Mostly approved records; analyst can lock for audit",
    },
    {
        "name": "Globex Corp",
        "slug": "globex",
        "email": "analyst@globex.com",
        "password": "demo123",
        "role": "analyst",
        "first_name": "Sam",
        "last_name": "Analyst",
        "description": "Reviewer view -- several needs_review records pending",
    },
    {
        "name": "Initech Ltd",
        "slug": "initech",
        "email": "admin@initech.com",
        "password": "demo123",
        "role": "admin",
        "first_name": "Pat",
        "last_name": "Admin",
        "description": "Shows error handling -- some failed rows visible",
    },
]


class Command(BaseCommand):
    help = "Seed 3 demo organizations with pre-ingested activity records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all existing demo data before seeding",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Resetting demo data...")
            for slug in ["acme", "globex", "initech"]:
                Organization.objects.filter(slug=slug).delete()
            self.stdout.write(self.style.WARNING("Demo data cleared."))

        # Load fixtures
        sap_content = (FIXTURES_DIR / "sap_sample.csv").read_bytes()
        utility_content = (FIXTURES_DIR / "utility_sample.csv").read_bytes()
        travel_payload = json.loads((FIXTURES_DIR / "travel_sample.json").read_text())

        for org_data in DEMO_ORGS:
            slug = org_data["slug"]
            self.stdout.write(f"\nSeeding {org_data['name']} ({slug})...")

            org, org_created = Organization.objects.get_or_create(
                slug=slug,
                defaults={"name": org_data["name"]},
            )
            if not org_created:
                self.stdout.write(f"  Organization '{slug}' already exists -- skipping.")
                continue

            user = User.objects.create_user(
                email=org_data["email"],
                organization=org,
                password=org_data["password"],
                role=org_data["role"],
                first_name=org_data["first_name"],
                last_name=org_data["last_name"],
            )
            self.stdout.write(f"  Created user: {user.email}")

            # Ingest all 3 source types for every org
            sap_result = ingest_sap(sap_content, "sap_sample.csv", org, user)
            self.stdout.write(
                f"  SAP: {sap_result.get('row_count', 0)} rows, "
                f"{sap_result.get('error_count', 0)} errors"
            )

            util_result = ingest_utility(utility_content, "utility_sample.csv", org, user)
            self.stdout.write(
                f"  Utility: {util_result.get('row_count', 0)} rows, "
                f"{util_result.get('error_count', 0)} errors"
            )

            travel_result = ingest_travel(travel_payload, "travel_q4_2024.json", org, user)
            self.stdout.write(
                f"  Travel: {travel_result.get('row_count', 0)} rows, "
                f"{travel_result.get('error_count', 0)} errors"
            )

            # For Acme: auto-approve the clean (green) records to showcase the lock flow
            if slug == "acme":
                green_records = ActivityRecord.objects.for_org(org).filter(
                    quality_tier="green", state="ingested"
                )
                approved = 0
                for rec in green_records:
                    rec._changed_by = user
                    rec.approve(user)
                    approved += 1
                self.stdout.write(
                    f"  Acme: auto-approved {approved} green records. "
                    f"Yellow/red records left in needs_review for demo."
                )

            self.stdout.write(self.style.SUCCESS(f"  {org_data['name']} seeded."))

        self.stdout.write(self.style.SUCCESS("\nSeed complete. Login credentials:"))
        for org_data in DEMO_ORGS:
            self.stdout.write(
                f"  {org_data['email']} / {org_data['password']} -- {org_data['name']}"
            )
