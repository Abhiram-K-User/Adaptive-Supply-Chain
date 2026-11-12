"""
Automated script to commit remaining features into Git with exactly 4 words per commit message.
Total 15 commits featurewise.
"""

import subprocess
import sys

COMMITS = [
    # Commit 4
    (
        ["adaptive_supply_chain_intelligence_prd.md", "DEMO_NEXT_STEPS.md"],
        "Add master roadmap specifications",
    ),
    # Commit 5
    (
        ["README.md", "pyproject.toml"],
        "Update repository configuration documentation",
    ),
    # Commit 6
    (
        ["scripts/verify_backend_frontend_connection.py", "scripts/make_commits.py"],
        "Add system verification script",
    ),
    # Commit 7
    (
        [
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/tsconfig.json",
            "frontend/tsconfig.tsbuildinfo",
            "frontend/index.html",
        ],
        "Configure frontend package dependencies",
    ),
    # Commit 8
    (
        [
            "frontend/tailwind.config.js",
            "frontend/src/index.css",
            "frontend/src/contexts/ThemeContext.tsx",
        ],
        "Implement enterprise theme system",
    ),
    # Commit 9
    (
        [
            "frontend/src/components/common/BrandLogo.tsx",
            "frontend/src/components/common/ThemeToggle.tsx",
            "frontend/src/components/common/KpiCard.tsx",
        ],
        "Add reusable brand components",
    ),
    # Commit 10
    (
        ["frontend/src/components/charts/Charts.tsx"],
        "Build business intelligence charts",
    ),
    # Commit 11
    (
        [
            "frontend/src/components/layout/Sidebar.tsx",
            "frontend/src/components/layout/TopNavbar.tsx",
            "frontend/src/components/layout/GlobalSearchModal.tsx",
            "frontend/src/components/layout/NotificationDrawer.tsx",
            "frontend/src/App.tsx",
            "frontend/src/main.tsx",
            "frontend/src/types/asci.ts",
            "frontend/src/components/HeaderBar.tsx",
            "frontend/src/components/OverviewCommandView.tsx",
        ],
        "Implement grid application shell",
    ),
    # Commit 12
    (
        [
            "frontend/src/pages/OverviewPage.tsx",
            "frontend/src/pages/NetworkPage.tsx",
            "frontend/src/components/NetworkView.tsx",
        ],
        "Add overview network modules",
    ),
    # Commit 13
    (
        [
            "frontend/src/pages/InventoryPage.tsx",
            "frontend/src/components/InventoryView.tsx",
            "frontend/src/pages/ForecastingPage.tsx",
            "frontend/src/components/ForecastingView.tsx",
        ],
        "Add inventory forecasting modules",
    ),
    # Commit 14
    (
        [
            "frontend/src/pages/SuppliersPage.tsx",
            "frontend/src/components/SuppliersView.tsx",
            "frontend/src/pages/RiskPage.tsx",
            "frontend/src/components/RiskView.tsx",
            "frontend/src/components/LiveFeedStrip.tsx",
        ],
        "Add supplier risk modules",
    ),
    # Commit 15
    (
        [
            "frontend/src/pages/OptimizationPage.tsx",
            "frontend/src/components/OptimizationView.tsx",
            "frontend/src/pages/AnalyticsPage.tsx",
            "frontend/src/components/AnalyticsView.tsx",
            "frontend/src/components/EvidenceView.tsx",
            "frontend/src/components/TraceView.tsx",
        ],
        "Add optimization analytics modules",
    ),
]

def run_git(args: list[str]) -> str:
    res = subprocess.run(["git"] + args, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Git command failed: git {' '.join(args)}")
        print(f"Stdout: {res.stdout}")
        print(f"Stderr: {res.stderr}")
        sys.exit(1)
    return res.stdout.strip()

def main():
    print("=" * 60)
    print("STARTING FEATUREWISE GIT COMMITS (4 WORDS EACH)")
    print("=" * 60)

    for i, (files, msg) in enumerate(COMMITS, start=4):
        words = msg.split()
        assert len(words) == 4, f"Commit message '{msg}' must have exactly 4 words, got {len(words)}"
        print(f"\n--- Commit {i}/15: '{msg}' ({len(words)} words) ---")
        for f in files:
            subprocess.run(["git", "add", f], check=False)
        run_git(["commit", "-m", msg])
        print(f"[OK] Committed: {msg}")

    print("\n" + "=" * 60)
    print("VERIFYING RECENT 15 COMMITS:")
    print("=" * 60)
    log_out = run_git(["log", "-n", "15", "--pretty=format:%h %s"])
    lines = log_out.splitlines()
    for line in lines:
        parts = line.split(" ", 1)
        commit_hash = parts[0]
        subject = parts[1] if len(parts) > 1 else ""
        word_count = len(subject.split())
        status = "PASS" if word_count == 4 else f"FAIL ({word_count} words)"
        print(f"  {commit_hash}  {subject:<50} [{status}]")

    print("\nAll remaining commits completed successfully!")

if __name__ == "__main__":
    main()

