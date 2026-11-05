#!/usr/bin/env python3
"""Generate per-organ template-config.yml and profile README files from organvm.config.json.

Reads the unified organvm.config.json and produces 7 per-organ
template-config.yml files + 8 profile-README.md files (7 organ + 1 meta).
The YAML configs are consumed by the .github repo's setup_template.py.
The profile READMEs are fully-resolved copies of .github-template/profile/README.md.

Usage:
    python scripts/generate-github-configs.py                        # Generate all 7 (YAML + profile READMEs)
    python scripts/generate-github-configs.py --organ ORGAN-I        # Generate one
    python scripts/generate-github-configs.py --dry-run              # Preview only
    python scripts/generate-github-configs.py --output-dir /tmp      # Custom output
    python scripts/generate-github-configs.py --no-profile-readmes   # YAML only

Requires: organvm.env.local to be sourced (for ORGAN_PREFIX and PERSONAL_ACCOUNT),
or pass --prefix and --account directly.
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

# Resolve paths relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = REPO_ROOT / ".config" / "organvm.config.json"
ENV_LOCAL_PATH = REPO_ROOT / ".config" / "organvm.env.local"
PROFILE_TEMPLATE_PATH = REPO_ROOT / ".github-template" / "profile" / "README.md"
META_RENDERER_PATH = SCRIPT_DIR / "generate-meta-profile.py"
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".github-template" / "generated"


def load_config(config_path: Path) -> dict:
    """Load organvm.config.json."""
    if not config_path.exists():
        print(f"Error: Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


def resolve_prefix(config: dict, cli_prefix: str | None) -> str:
    """Resolve ORGAN_PREFIX from CLI arg, env var, or env.local file."""
    if cli_prefix:
        return cli_prefix
    if os.environ.get("ORGAN_PREFIX"):
        return os.environ["ORGAN_PREFIX"]
    # Try parsing env.local
    if ENV_LOCAL_PATH.exists():
        for line in ENV_LOCAL_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("ORGAN_PREFIX="):
                return line.split("=", 1)[1].strip('"').strip("'")
    # Fall back to template default
    prefix = config.get("organ_prefix", "organvm")
    if "${" in prefix:
        return "organvm"
    return prefix


def resolve_personal_account(cli_account: str | None) -> str:
    """Resolve PERSONAL_ACCOUNT from CLI arg, env var, or env.local file."""
    if cli_account:
        return cli_account
    if os.environ.get("PERSONAL_ACCOUNT"):
        return os.environ["PERSONAL_ACCOUNT"]
    if ENV_LOCAL_PATH.exists():
        for line in ENV_LOCAL_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("PERSONAL_ACCOUNT="):
                return line.split("=", 1)[1].strip('"').strip("'")
    return ""


def resolve_vars(value: str, prefix: str, account: str) -> str:
    """Replace ${ORGAN_PREFIX} and ${PERSONAL_ACCOUNT} in a string."""
    return value.replace("${ORGAN_PREFIX}", prefix).replace("${PERSONAL_ACCOUNT}", account)


def generate_template_config(organ_key: str, organ: dict, shared: dict, prefix: str, account: str) -> str:
    """Generate a template-config.yml string for one organ."""
    org_name = f"{prefix}-{organ['suffix']}"
    display_name = organ.get("display_name", organ_key)
    email_domain = shared.get("email_domain", "example.org")
    license_type = organ.get("license", shared.get("license_default", "MIT"))
    features = organ.get("features", {})

    # Resolve team names
    teams = shared.get("teams", {})
    team_leadership = resolve_vars(teams.get("leadership", f"{prefix}-leads"), prefix, account)
    team_engineering = resolve_vars(teams.get("engineering", f"{prefix}-engineering"), prefix, account)
    team_devops = resolve_vars(teams.get("devops", f"{prefix}-devops"), prefix, account)
    team_security = resolve_vars(teams.get("security", f"{prefix}-security"), prefix, account)

    lines = [
        f"# Template Configuration for {display_name}",
        "# Generated from organvm.config.json — do not edit manually",
        f"# Re-generate with: python scripts/generate-github-configs.py --organ {organ_key}",
        "",
        "# Organization Settings",
        "org:",
        f"  name: '{org_name}'",
        f"  display_name: '{display_name}'",
        f"  website: 'https://github.com/{org_name}'",
        f"  email_domain: '{email_domain}'",
        "",
        "# Repository Settings",
        "repo:",
        "  name: '.github'",
        f"  npm_scope: '{org_name}'",
        "",
        "# Social/Community",
        "social:",
        f"  discord_invite: '{shared.get('discord_invite', '')}'",
        "",
        "# Contact Emails",
        "emails:",
        f"  support: support@{email_domain}",
        f"  security: security@{email_domain}",
        f"  conduct: conduct@{email_domain}",
        "",
        "# Team Names (used in CODEOWNERS)",
        "teams:",
        f"  leadership: '{team_leadership}'",
        f"  engineering: '{team_engineering}'",
        f"  devops: '{team_devops}'",
        f"  security: '{team_security}'",
        "",
        "# Product/Application Settings",
        "product:",
        f"  name: '{display_name}'",
        "  api_endpoint: ''",
        "",
        "# Default Tool Versions",
        "defaults:",
        "  python_version: '3.12'",
        "  node_version: '20'",
        "  go_version: '1.22'",
        "  rust_version: stable",
        "",
        "# Template Metadata",
        "template:",
        "  version: 1.0.0",
        f"  source: https://github.com/{org_name}/.github",
        f"  description: '{display_name} — organization-wide GitHub configuration'",
        "",
        "# Feature Flags",
        "features:",
        f"  ai_agents: {'true' if features.get('ai_agents') else 'false'}",
        f"  advanced_ci: {'true' if features.get('advanced_ci') else 'false'}",
        f"  security_scanning: {'true' if features.get('security_scanning') else 'false'}",
        f"  automated_releases: {'true' if features.get('automated_releases') else 'false'}",
        f"  demo_sandbox: {'true' if features.get('demo_sandbox') else 'false'}",
        f"  documentation_site: {'true' if features.get('documentation_site') else 'false'}",
        "  slack_notifications: false",
        f"  ml_workflows: {'true' if features.get('ml_workflows') else 'false'}",
        "",
        "# Cross-Org References (resolved from shared.cross_refs)",
        "cross_refs:",
        f"  taxis_org: '{resolve_vars(shared.get('cross_refs', {}).get('taxis_org', f'{prefix}-iv-taxis'), prefix, account)}'",
        "",
        "# Organ-Specific Metadata (not consumed by setup_template.py, for reference)",
        "organ:",
        f"  key: '{organ_key}'",
        f"  domain: '{organ.get('domain', '')}'",
        f"  etymology: '{organ.get('etymology', '')}'",
        f"  license: '{license_type}'",
        f"  tagline: '{organ.get('profile_tagline', '')}'",
        f"  description: '{organ.get('description', '')}'",
        "",
    ]
    return "\n".join(lines)


def generate_profile_readme(organ_key: str, organ: dict, all_orgs: dict, prefix: str, shared: dict, meta_org_name: str) -> str:
    """Generate a fully-resolved profile README for one organ.

    Reads the template from .github-template/profile/README.md and resolves
    all {{VAR}} placeholders, including the org table which requires all orgs + meta.
    """
    if not PROFILE_TEMPLATE_PATH.exists():
        print(f"Warning: Profile template not found: {PROFILE_TEMPLATE_PATH}", file=sys.stderr)
        return ""

    template = PROFILE_TEMPLATE_PATH.read_text()
    org_name = f"{prefix}-{organ['suffix']}"
    taxis_org = resolve_vars(
        shared.get("cross_refs", {}).get("taxis_org", f"{prefix}-iv-taxis"),
        prefix, "",
    )

    # Simple placeholder substitutions
    result = template.replace("{{ORG_DISPLAY_NAME}}", organ.get("display_name", organ_key))
    result = result.replace("{{ORGAN_ETYMOLOGY}}", organ.get("etymology", ""))
    result = result.replace("{{ORGAN_TAGLINE}}", organ.get("profile_tagline", ""))
    result = result.replace("{{ORGAN_DESCRIPTION}}", organ.get("description", ""))
    result = result.replace("{{ORG_NAME}}", org_name)
    result = result.replace("{{TAXIS_ORG}}", taxis_org)
    result = result.replace("{{META_ORG}}", meta_org_name)
    result = result.replace("{{CONDUCT_EMAIL}}", f"conduct@{shared.get('email_domain', 'example.org')}")
    result = result.replace("{{SUPPORT_EMAIL}}", f"support@{shared.get('email_domain', 'example.org')}")

    # Build the org table with all 8 orgs resolved (7 organs + meta)
    roman = ["I", "II", "III", "IV", "V", "VI", "VII"]
    table_lines = [
        "| Organ | Domain | Organization |",
        "|-------|--------|-------------|",
    ]
    for i, (key, org) in enumerate(all_orgs.items()):
        full_name = f"{prefix}-{org['suffix']}"
        domain = org.get("domain", "")
        numeral = roman[i] if i < len(roman) else key
        table_lines.append(f"| {numeral} | {domain} | [{full_name}](https://github.com/{full_name}) |")
    # Add meta-org row
    table_lines.append(f"| VIII | Meta | [{meta_org_name}](https://github.com/{meta_org_name}) |")

    # Replace the hardcoded table in the template
    table_pattern = r'\| Organ \| Domain \| Organization \|.*?(?=\n\n|\n---|\Z)'
    result = re.sub(table_pattern, "\n".join(table_lines), result, flags=re.DOTALL)

    return result


def generate_meta_profile_readme(config: dict, prefix: str) -> str:
    """Use the owning renderer and current sources for the shared meta projection.

    This command writes the same file as generate-meta-profile.py. A separate
    config-only renderer would overwrite its sourced metrics and editorial copy.
    """
    spec = importlib.util.spec_from_file_location("organvm_meta_profile", META_RENDERER_PATH)
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    return renderer.render(
        config,
        renderer.load_json(renderer.REGISTRY_PATH),
        renderer.load_json(renderer.METRICS_PATH),
        renderer.load_json(renderer.SNAPSHOT_PATH),
        prefix=prefix,
    )


def main():
    parser = argparse.ArgumentParser(description="Generate per-organ template-config.yml files.")
    parser.add_argument("--organ", help="Generate for a single organ (e.g., ORGAN-I)")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout instead of writing files")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--prefix", help="Override ORGAN_PREFIX (default: from env.local or env)")
    parser.add_argument("--account", help="Override PERSONAL_ACCOUNT")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="Path to organvm.config.json")
    parser.add_argument("--no-profile-readmes", action="store_true", help="Skip profile README generation")
    args = parser.parse_args()

    config = load_config(args.config)
    prefix = resolve_prefix(config, args.prefix)
    account = resolve_personal_account(args.account)
    shared = config.get("shared", {})
    orgs = config.get("orgs", {})

    if args.organ:
        if args.organ not in orgs:
            print(f"Error: Unknown organ '{args.organ}'. Valid: {', '.join(orgs.keys())}", file=sys.stderr)
            sys.exit(1)
        targets = {args.organ: orgs[args.organ]}
    else:
        targets = orgs

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    for organ_key, organ_data in targets.items():
        content = generate_template_config(organ_key, organ_data, shared, prefix, account)
        org_name = f"{prefix}-{organ_data['suffix']}"
        filename = f"{org_name}.template-config.yml"

        if args.dry_run:
            print(f"--- {filename} ---")
            print(content)
        else:
            out_path = args.output_dir / filename
            out_path.write_text(content)
            print(f"  Generated: {out_path}")

    # Generate profile READMEs (needs all orgs for the table)
    profile_count = 0
    meta_org_name = resolve_vars(
        shared.get("cross_refs", {}).get("meta_org", f"meta-{prefix}"),
        prefix, "",
    )
    if not args.no_profile_readmes:
        for organ_key, organ_data in targets.items():
            readme_content = generate_profile_readme(organ_key, organ_data, orgs, prefix, shared, meta_org_name)
            if not readme_content:
                continue
            org_name = f"{prefix}-{organ_data['suffix']}"
            readme_filename = f"{org_name}.profile-README.md"

            if args.dry_run:
                print(f"--- {readme_filename} ---")
                print(readme_content)
            else:
                readme_path = args.output_dir / readme_filename
                readme_path.write_text(readme_content)
                print(f"  Generated: {readme_path}")
            profile_count += 1

    # Generate meta-org profile README
    meta_generated = False
    if not args.no_profile_readmes and not args.organ:
        meta_content = generate_meta_profile_readme(config, prefix)
        if meta_content:
            meta_org = resolve_vars(
                shared.get("cross_refs", {}).get("meta_org", f"meta-{prefix}"),
                prefix, "",
            )
            meta_filename = f"{meta_org}.profile-README.md"
            if args.dry_run:
                print(f"--- {meta_filename} ---")
                print(meta_content)
            else:
                meta_path = args.output_dir / meta_filename
                meta_path.write_text(meta_content)
                print(f"  Generated: {meta_path}")
            profile_count += 1
            meta_generated = True

    if not args.dry_run:
        len(targets) + profile_count
        meta_note = " (includes meta-org)" if meta_generated else ""
        print(f"\nGenerated {len(targets)} config(s) + {profile_count} profile README(s){meta_note} in {args.output_dir}/")
        print("Next: copy each config to the target .github repo as .config/template-config.yml")
        print("      copy each profile README to the target .github repo as profile/README.md")
        print("Then: python src/automation/scripts/setup_template.py")


if __name__ == "__main__":
    main()
