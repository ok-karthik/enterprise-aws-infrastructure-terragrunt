import os
import sys
import subprocess
import zipfile
import io
from pathlib import Path
from typing import Optional
import requests
from openai import OpenAI

# ==========================================
# 1. Environment & API Setup
# ==========================================
# These variables are automatically injected by the GitHub Actions environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
FAILED_RUN_ID = os.getenv("FAILED_RUN_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# GitHub Repository name is usually formatted as "owner/repo" (e.g. "ok-karthik/enterprise-aws-platform-terragrunt")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")

if not GITHUB_TOKEN or not FAILED_RUN_ID or not GITHUB_REPOSITORY:
    print("❌ Error: Missing required GitHub Actions environment variables.")
    sys.exit(1)

if not GROQ_API_KEY:
    print("❌ Error: GROQ_API_KEY is not set.")
    sys.exit(1)

# Initialize OpenAI-compatible client targeting Groq
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

# Resolve paths relative to this script
BASE_DIR = Path(__file__).parent.parent if "__file__" in locals() else Path(".")
CI_HEALER_PROMPT_PATH = BASE_DIR / "prompts" / "ci_healer.md"


# ==========================================
# 2. Fetch Failed Logs from GitHub API
# ==========================================
def get_failed_job_names(run_id: str, repo: str, token: str) -> list[str]:
    """Queries the GitHub API to find which specific jobs failed in the run."""
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return [job["name"] for job in data.get("jobs", []) if job.get("conclusion") == "failure"]
    except Exception as e:
        print(f"⚠️ Failed to query jobs list: {e}")
    return []


def is_log_for_failed_job(filename: str, failed_jobs: list[str]) -> bool:
    """Matches zip log filenames (like 'Dev___Plan__dev.txt') to failed job names."""
    if not failed_jobs:
        return True # Fallback: match all files if we couldn't fetch job list

    # Clean filename (strip extension and replace spacers)
    clean_file = filename.replace(".txt", "").replace("_", " ").replace("-", " ").lower()
    for job in failed_jobs:
        clean_job = job.replace("/", " ").replace(":", " ").replace("-", " ").lower()
        words_file = set(clean_file.split())
        words_job = set(clean_job.split())
        # If words match significantly, we have a match
        if words_job.issubset(words_file) or words_file.issubset(words_job):
            return True
    return False


def download_failed_logs(run_id: str, repo: str, token: str) -> str:
    """
    Downloads the execution logs for a specific GitHub workflow run.
    Extracts and filters logs only for the specific jobs that failed.
    """
    # 1. Query the failed jobs list
    failed_jobs = get_failed_job_names(run_id, repo, token)
    print(f"🔍 Failed jobs identified on GitHub: {failed_jobs}")

    print(f"📥 Fetching log archive for run ID: {run_id}...")
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    response = requests.get(url, headers=headers, stream=True)
    if response.status_code != 200:
        print(f"❌ Failed to fetch logs. API Status: {response.status_code}")
        sys.exit(1)

    zip_file_bytes = io.BytesIO(response.content)
    log_contents = []
    error_keywords = ["error", "fail", "exit status", "violat", "deny", "exception"]

    with zipfile.ZipFile(zip_file_bytes, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            # Check main text logs and filter by failed job matching
            if file_info.filename.endswith(".txt") and not "/" in file_info.filename:
                if is_log_for_failed_job(file_info.filename, failed_jobs):
                    with zip_ref.open(file_info.filename) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        content_lower = content.lower()

                        # Only keep logs that contain an indication of failure
                        if any(kw in content_lower for kw in error_keywords):
                            # Keep the last 100 lines (we can afford more lines since we only read failed jobs)
                            lines = content.splitlines()[-100:]
                            log_contents.append(f"=== Job Log: {file_info.filename} ===\n" + "\n".join(lines))
                        else:
                            print(f"ℹ️ Skipping clean log file: {file_info.filename}")
                else:
                    print(f"ℹ️ Skipping successful job log: {file_info.filename}")

    logs = "\n\n".join(log_contents)
    print(f"📊 Prepared log payload size: {len(logs)} characters (~{len(logs) // 4} tokens)")
    return logs


# ==========================================
# 3. Main Agent Loop
# ==========================================
def run_lock_file_upgrade() -> bool:
    """Finds all active .terraform.lock.hcl files and runs terragrunt providers lock --upgrade on them."""
    lock_files = []
    # Walk the repository and locate active lock files (skip cache and git directories)
    for root, dirs, files in os.walk("."):
        if ".terragrunt-cache" in root or ".git" in root or ".agents" in root:
            continue
        if ".terraform.lock.hcl" in files:
            lock_files.append(Path(root) / ".terraform.lock.hcl")

    if not lock_files:
        print("⚠️ No .terraform.lock.hcl files found in the repository.")
        return False

    changes_made = False
    for lock_file in lock_files:
        working_dir = lock_file.parent
        print(f"⚙️ Running terragrunt providers lock --upgrade in {working_dir}...")
        res = subprocess.run(
            ["terragrunt", "providers", "lock", "--upgrade", "--terragrunt-non-interactive"],
            cwd=str(working_dir),
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            print(f"⚠️ Failed to upgrade lock file in {working_dir}. Stderr:\n{res.stderr}")
        else:
            print(f"✅ Upgraded lock file in {working_dir}")
            changes_made = True

    # Check if files actually changed on disk
    diff_res = subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True)
    if diff_res.stdout.strip():
        print("📊 Lock files successfully upgraded. Changes detected:")
        print(diff_res.stdout)
        return True

    print("ℹ️ Lock files are already up-to-date. No diff detected.")
    return False


def commit_and_push_changes(commit_message: str) -> bool:
    """Stages all local modifications, commits them, and pushes to the PR branch."""
    head_branch = os.getenv("HEAD_BRANCH")
    if not head_branch:
        print("⚠️ HEAD_BRANCH env var is not set. Skipping git commit/push.")
        return False

    print(f"🚀 Committing and pushing fixes to branch: {head_branch}...")
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"])
    subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])

    # Stage modifications
    subprocess.run(["git", "add", "-A"])

    # Commit changes
    commit_res = subprocess.run(
        ["git", "commit", "-m", commit_message],
        capture_output=True, text=True
    )
    if commit_res.returncode != 0:
        print(f"⚠️ Commit skipped (no changes detected or git error): {commit_res.stdout}")
        return False

    # Push to origin
    push_res = subprocess.run(["git", "push", "origin", head_branch], capture_output=True, text=True)
    if push_res.returncode != 0:
        print(f"❌ Failed to push changes to branch {head_branch}. Error:\n{push_res.stderr}")
        return False

    print("🎉 Successfully pushed remediation commit to the PR branch!")
    return True


def main():
    # 0. Set Git safe directory flags system-wide and globally to prevent dubious ownership issues
    subprocess.run(["git", "config", "--system", "--add", "safe.directory", "*"], capture_output=True)
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True)

    # 1. Download logs
    failed_logs = download_failed_logs(FAILED_RUN_ID, GITHUB_REPOSITORY, GITHUB_TOKEN)
    if not failed_logs.strip():
        print("⚠️ No log files found in the archive.")
        sys.exit(0)

    # Check if this is a Terraform Provider Lock file mismatch issue
    if "does not match configured version constraint" in failed_logs or "must use terraform init -upgrade" in failed_logs:
        print("🛟 [Healer] Detected Terraform Provider Lock mismatch. Attempting automatic lock file upgrades...")
        lock_fixed = run_lock_file_upgrade()
        if lock_fixed:
            commit_and_push_changes("chore(ci): auto-upgrade terraform provider lock files")
            sys.exit(0)
        else:
            print("⚠️ Lock file upgrade did not produce filesystem changes. Falling back to LLM patch...")

    # 2. Load system prompt instructions
    if not CI_HEALER_PROMPT_PATH.exists():
        print(f"❌ System prompt file not found at: {CI_HEALER_PROMPT_PATH}")
        sys.exit(1)
    system_prompt = CI_HEALER_PROMPT_PATH.read_text().strip()

    # 2.5 Generate a compact project tree representation
    project_files = []
    for root, dirs, files in os.walk("."):
        # Prune search in-place to avoid descending into unwanted directories
        dirs[:] = [d for d in dirs if d not in (".git", ".github", ".terragrunt-cache", ".agents", "venv", ".venv")]
        for file in sorted(files):
            if file.endswith((".tf", ".hcl", ".tfvars", ".yaml", ".yml")) or file in ("Dockerfile", "Makefile", "renovate.json"):
                path = Path(root) / file
                try:
                    project_files.append(str(path.relative_to(".")))
                except ValueError:
                    project_files.append(str(path))

    project_tree = "\n".join(sorted(project_files))

    print("\n🧠 [Healer Agent] Analyzing logs with Groq (llama-3.3-70b-versatile)...")

    user_payload = (
        f"The pipeline crashed with these logs:\n\n{failed_logs}\n\n"
        f"Here is the project tree layout (relevant files only):\n"
        f"```\n{project_tree}\n```"
    )

    # 3. Call Groq LLM
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload}
        ],
        temperature=0.1
    )

    patch_code = response.choices[0].message.content.strip()

    print("\n🛡️ Generated Patch / Recommendation:")
    print("==========================================")
    print(patch_code)
    print("==========================================")

    # 4. Extract and apply the patch to the PR branch
    apply_and_push_patch(patch_code)


def extract_diff(text: str) -> Optional[str]:
    """Extracts the first diff block from the LLM markdown response."""
    import re
    # Match code blocks labeled diff or standard code blocks containing diff headers
    match = re.search(r"```(?:diff)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        block = match.group(1)
        if "--- " in block and "+++" in block:
            return block
    # Fallback if no block tags are found but diff headers exist
    if "--- " in text:
        match_raw = re.search(r"(--- a/.*)", text, re.DOTALL)
        if match_raw:
            return match_raw.group(1)
    return None


def apply_and_push_patch(patch_code: str):
    """Parses, applies, and pushes the patch to the source branch."""
    diff_text = extract_diff(patch_code)
    if not diff_text:
        print("⚠️ Could not extract a valid git diff block from the agent response. Skipping auto-remediation.")
        return

    patch_path = Path("patch_proposal.diff")
    patch_path.write_text(diff_text)
    print("💾 Saved clean diff block to patch_proposal.diff")

    # 1. Apply the patch locally
    res = subprocess.run(["git", "apply", str(patch_path)], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ Failed to apply patch using git apply. Error:\n{res.stderr}")
        return
    print("✅ Successfully applied git patch locally.")

    # 2. Commit and push the applied patch
    commit_and_push_changes("chore(ci): auto-remediate pipeline failure")


if __name__ == "__main__":
    main()
